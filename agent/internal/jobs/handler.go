package jobs

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"deploybot-agent/internal/audit"
	"deploybot-agent/internal/config"
	"deploybot-agent/internal/dockerutil"
	"deploybot-agent/internal/git"
	"deploybot-agent/internal/state"

	"github.com/compose-spec/compose-go/loader"
	composetypes "github.com/compose-spec/compose-go/types"
	"github.com/docker/docker/api/types/container"
)

// LogPublisher streams logs back to the controller.
type LogPublisher interface {
	Publish(ctx context.Context, jobID string, reader io.Reader) error
}

// Handler executes controller jobs.
type Handler struct {
	Cfg          config.Config
	State        *state.Store
	Docker       *dockerutil.Manager
	LogPublisher LogPublisher
	Audit        *audit.Logger
}

// Handle executes a job and returns optional detail for acknowledgements.
func (h *Handler) Handle(ctx context.Context, job *Job) (interface{}, error) {
	start := time.Now()
	h.audit("job.start", map[string]interface{}{"job_id": job.ID, "job_type": job.Type})
	var result interface{}
	var err error
	switch job.Type {
	case JobDeploy:
		var payload DeployJobPayload
		if err = json.Unmarshal(job.Payload, &payload); err == nil {
			result, err = h.handleDeploy(ctx, job.ID, payload)
		}
	case JobRestart:
		var payload ContainerJobPayload
		if err = json.Unmarshal(job.Payload, &payload); err == nil {
			err = h.Docker.Restart(ctx, payload.Container)
		}
	case JobStop:
		var payload ContainerJobPayload
		if err = json.Unmarshal(job.Payload, &payload); err == nil {
			err = h.Docker.Stop(ctx, payload.Container)
		}
	case JobRemove:
		var payload ContainerJobPayload
		if err = json.Unmarshal(job.Payload, &payload); err == nil {
			err = h.Docker.Remove(ctx, payload.Container, true)
		}
	case JobLogs:
		result, err = h.handleLogs(ctx, job)
	case JobExec:
		var payload ExecJobPayload
		if err = json.Unmarshal(job.Payload, &payload); err == nil {
			result, err = h.handleExec(ctx, payload)
		}
	case JobQueryEnv:
		var payload EnvQueryPayload
		if err = json.Unmarshal(job.Payload, &payload); err == nil {
			result, err = h.handleEnvQuery(payload)
		}
	default:
		err = fmt.Errorf("unsupported job type: %s", job.Type)
	}
	duration := time.Since(start)
	status := "succeeded"
	fields := map[string]interface{}{"job_id": job.ID, "job_type": job.Type, "duration_ms": duration.Milliseconds()}
	if err != nil {
		status = "failed"
		fields["error"] = err.Error()
	}
	fields["status"] = status
	h.audit("job.finish", fields)
	return result, err
}

func (h *Handler) handleDeploy(ctx context.Context, jobID string, payload DeployJobPayload) (interface{}, error) {
	// For image-only deployments, skip repository operations
	if strings.ToLower(payload.Strategy) == "image" || (payload.Image != "" && payload.RepositoryURL == "") {
		if payload.Image == "" {
			return nil, errors.New("image strategy requires image field")
		}
		if payload.Name == "" {
			payload.Name = sanitizeName(payload.Image)
			if payload.Name == "" {
				payload.Name = "deploy"
			}
		}
		strategy := strategySelection{kind: strategyImage, image: payload.Image}
		return h.deployImage(ctx, "", payload, strategy)
	}

	// Repository-based deployments require repository_url
	if payload.RepositoryURL == "" {
		return nil, errors.New("deploy job missing repository_url")
	}
	if payload.Ref == "" {
		payload.Ref = "main"
	}
	if payload.Name == "" {
		payload.Name = sanitizeName(filepath.Base(payload.RepositoryURL))
		if payload.Name == "" {
			payload.Name = "deploy"
		}
	}
	workspace := git.WorkspacePath(h.Cfg.WorkDir, payload.RepositoryURL, payload.Ref)
	if err := os.MkdirAll(filepath.Dir(workspace), 0o755); err != nil {
		return nil, err
	}
	cleanupWorkspace := h.Cfg.CleanupWorkspaces && h.securityEnabled()
	if cleanupWorkspace {
		defer h.cleanupWorkspace(workspace)
	}
	cloneCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()
	if err := git.ShallowClone(cloneCtx, payload.RepositoryURL, payload.Ref, workspace); err != nil {
		return nil, fmt.Errorf("clone failed: %w", err)
	}
	if h.securityEnabled() && payload.CommitSHA != "" {
		if err := git.VerifyHEAD(workspace, payload.CommitSHA); err != nil {
			return nil, err
		}
	}
	strategy, err := determineStrategy(workspace, payload)
	if err != nil {
		return nil, err
	}
	switch strategy.kind {
	case strategyCompose:
		return h.deployCompose(ctx, workspace, payload, strategy)
	case strategyDeployJSON:
		return h.deployDescriptor(ctx, workspace, payload, strategy)
	case strategyDockerfile:
		return h.deployDockerfile(ctx, workspace, payload, strategy)
	case strategyImage:
		return h.deployImage(ctx, workspace, payload, strategy)
	default:
		return nil, fmt.Errorf("strategy %v not supported", strategy.kind)
	}
}

func (h *Handler) handleLogs(ctx context.Context, job *Job) (interface{}, error) {
	if h.LogPublisher == nil {
		return nil, errors.New("log publisher not configured")
	}
	var payload LogsJobPayload
	if err := json.Unmarshal(job.Payload, &payload); err != nil {
		return nil, err
	}
	tail := payload.Tail
	if tail <= 0 {
		tail = 200
	}
	followDuration := time.Duration(payload.FollowMins)
	if followDuration <= 0 {
		followDuration = h.Cfg.LogsFollowDuration
	} else {
		followDuration *= time.Minute
	}
	ctxLogs, cancel := context.WithTimeout(ctx, followDuration)
	defer cancel()
	reader, err := h.Docker.Logs(ctxLogs, payload.Container, tail, true)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	if err := h.LogPublisher.Publish(ctxLogs, job.ID, reader); err != nil {
		return nil, err
	}
	return map[string]any{"followed_minutes": followDuration.Minutes()}, nil
}

func (h *Handler) handleExec(ctx context.Context, payload ExecJobPayload) (interface{}, error) {
	if !h.Cfg.AllowUnsafeCommands && h.securityEnabled() {
		return nil, errors.New("exec jobs disabled by configuration")
	}
	if len(payload.Command) == 0 {
		return nil, errors.New("exec job missing command")
	}
	execCtx := ctx
	var cancel context.CancelFunc
	if payload.TimeoutSeconds > 0 {
		execCtx, cancel = context.WithTimeout(ctx, time.Duration(payload.TimeoutSeconds)*time.Second)
		defer cancel()
	}
	cmd := exec.CommandContext(execCtx, payload.Command[0], payload.Command[1:]...)
	if payload.WorkingDir != "" {
		cmd.Dir = payload.WorkingDir
	}
	if len(payload.Environment) > 0 {
		cmd.Env = append(os.Environ(), mapToEnvSlice(payload.Environment)...)
	}
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	err := cmd.Run()
	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			return nil, err
		}
	}
	result := map[string]interface{}{"exit_code": exitCode, "stdout": limitOutput(stdout.String()), "stderr": limitOutput(stderr.String())}
	if err != nil {
		return result, err
	}
	return result, nil
}

func (h *Handler) handleEnvQuery(payload EnvQueryPayload) (interface{}, error) {
	if !h.Cfg.AllowUnsafeCommands && h.securityEnabled() {
		return nil, errors.New("environment queries disabled by configuration")
	}
	response := map[string]string{}
	for _, key := range payload.Keys {
		response[key] = os.Getenv(key)
	}
	return response, nil
}

func (h *Handler) cleanupWorkspace(path string) {
	if path == "" {
		return
	}
	if err := os.RemoveAll(path); err != nil {
		h.audit("workspace.cleanup_failed", map[string]interface{}{"path": path, "error": err.Error()})
	} else {
		h.audit("workspace.cleaned", map[string]interface{}{"path": path})
	}
}

func (h *Handler) audit(event string, fields map[string]interface{}) {
	if h.Audit == nil {
		return
	}
	if fields == nil {
		fields = map[string]interface{}{}
	}
	_ = h.Audit.Log(event, fields)
}

func (h *Handler) securityEnabled() bool { return !h.Cfg.SecurityBypass }

func (h *Handler) enforceImagePolicy(image string) error {
	if !h.securityEnabled() || image == "" {
		return nil
	}
	if len(h.Cfg.RegistryAllowList) > 0 {
		registry := imageRegistry(image)
		allowed := false
		for _, candidate := range h.Cfg.RegistryAllowList {
			if strings.EqualFold(registry, strings.TrimSpace(candidate)) {
				allowed = true
				break
			}
		}
		if !allowed {
			return fmt.Errorf("image registry %s not allowlisted", registry)
		}
	}
	if h.Cfg.RequireImageDigest && digestFromReference(image) == "" {
		return fmt.Errorf("image %s must be pinned by digest", image)
	}
	return nil
}

func (h *Handler) validateVolumeSource(source string) error {
	if !h.securityEnabled() || len(h.Cfg.AllowedVolumeRoots) == 0 || source == "" {
		return nil
	}
	absolute, err := filepath.Abs(source)
	if err != nil {
		return err
	}
	for _, root := range h.Cfg.AllowedVolumeRoots {
		rootClean := strings.TrimSpace(root)
		if rootClean == "" {
			continue
		}
		rootAbs, err := filepath.Abs(rootClean)
		if err != nil {
			continue
		}
		if strings.HasPrefix(absolute, rootAbs) {
			return nil
		}
	}
	return fmt.Errorf("volume source %s outside allowed roots", source)
}

func (h *Handler) verifyImageDigest(ctx context.Context, image, expected string) error {
	if !h.securityEnabled() || !h.Cfg.RequireImageDigest {
		return nil
	}
	normalizedExpected := normalizeDigest(expected)
	if normalizedExpected == "" {
		normalizedExpected = digestFromReference(image)
	}
	if normalizedExpected == "" {
		return fmt.Errorf("image digest required for %s", image)
	}
	if err := h.Docker.EnsureImage(ctx, image); err != nil {
		return err
	}
	digest, err := h.Docker.ImageDigest(ctx, image)
	if err != nil {
		return err
	}
	actual := normalizeDigest(digest)
	if actual == "" {
		return fmt.Errorf("unable to resolve digest for image %s", image)
	}
	if actual != normalizedExpected {
		return fmt.Errorf("image digest mismatch: expected %s got %s", normalizedExpected, actual)
	}
	return nil
}

func mapToEnvSlice(env map[string]string) []string {
	if len(env) == 0 {
		return nil
	}
	keys := make([]string, 0, len(env))
	for k := range env {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make([]string, 0, len(env))
	for _, k := range keys {
		out = append(out, fmt.Sprintf("%s=%s", k, env[k]))
	}
	return out
}

func limitOutput(value string) string {
	const max = 16384
	if len(value) <= max {
		return value
	}
	return value[:max] + "...<truncated>"
}

func normalizeDigest(digest string) string {
	trimmed := strings.TrimSpace(strings.ToLower(digest))
	if trimmed == "" {
		return ""
	}
	if strings.HasPrefix(trimmed, "sha256:") {
		return trimmed
	}
	if len(trimmed) == 64 && isHex(trimmed) {
		return "sha256:" + trimmed
	}
	return trimmed
}

func digestFromReference(ref string) string {
	if ref == "" {
		return ""
	}
	if idx := strings.Index(ref, "@"); idx >= 0 {
		return normalizeDigest(ref[idx+1:])
	}
	return ""
}

func imageRegistry(ref string) string {
	parts := strings.Split(ref, "/")
	if len(parts) == 0 {
		return ""
	}
	candidate := parts[0]
	if strings.Contains(candidate, ":") || strings.Contains(candidate, ".") || candidate == "localhost" {
		return candidate
	}
	return "docker.io"
}

func isHex(s string) bool {
	for _, r := range s {
		if (r >= '0' && r <= '9') || (r >= 'a' && r <= 'f') {
			continue
		}
		return false
	}
	return true
}

// Compose helpers and deploy strategies
type strategyKind int

const (
	strategyCompose strategyKind = iota
	strategyDeployJSON
	strategyDockerfile
	strategyImage
)

type strategySelection struct {
	kind        strategyKind
	composeFile string
	descriptor  string
	dockerfile  string
	image       string
}

func determineStrategy(workdir string, payload DeployJobPayload) (strategySelection, error) {
	switch strings.ToLower(payload.Strategy) {
	case "compose":
		if payload.ComposeFile != "" {
			return strategySelection{kind: strategyCompose, composeFile: payload.ComposeFile}, nil
		}
	case "deploy.json", "descriptor":
		return strategySelection{kind: strategyDeployJSON, descriptor: "deploy.json"}, nil
	case "dockerfile":
		dockerfile := payload.Dockerfile
		if dockerfile == "" {
			dockerfile = "Dockerfile"
		}
		return strategySelection{kind: strategyDockerfile, dockerfile: dockerfile}, nil
	case "image":
		if payload.Image == "" {
			return strategySelection{}, fmt.Errorf("strategy image selected but image is empty")
		}
		return strategySelection{kind: strategyImage, image: payload.Image}, nil
	}
	if payload.ComposeFile != "" {
		return strategySelection{kind: strategyCompose, composeFile: payload.ComposeFile}, nil
	}
	composeCandidates := []string{"deploy.compose.yml", "deploy.compose.yaml", "docker-compose.yml", "docker-compose.yaml"}
	for _, candidate := range composeCandidates {
		path := filepath.Join(workdir, candidate)
		if fileExists(path) {
			return strategySelection{kind: strategyCompose, composeFile: candidate}, nil
		}
	}
	desc := filepath.Join(workdir, "deploy.json")
	if fileExists(desc) {
		return strategySelection{kind: strategyDeployJSON, descriptor: "deploy.json"}, nil
	}
	dockerfile := payload.Dockerfile
	if dockerfile == "" {
		dockerfile = "Dockerfile"
	}
	if fileExists(filepath.Join(workdir, dockerfile)) {
		return strategySelection{kind: strategyDockerfile, dockerfile: dockerfile}, nil
	}
	if payload.Image != "" {
		return strategySelection{kind: strategyImage, image: payload.Image}, nil
	}
	return strategySelection{}, fmt.Errorf("no deployment artefact found in %s", workdir)
}

func (h *Handler) deployCompose(ctx context.Context, workdir string, payload DeployJobPayload, selection strategySelection) (interface{}, error) {
	details := composetypes.ConfigDetails{
		WorkingDir:  workdir,
		ConfigFiles: []composetypes.ConfigFile{{Filename: filepath.Join(workdir, selection.composeFile)}},
		Environment: map[string]string{},
	}
	project, err := loader.Load(details)
	if err != nil {
		return nil, fmt.Errorf("compose load failed: %w", err)
	}
	if project.Name == "" {
		project.Name = strings.TrimSuffix(filepath.Base(workdir), filepath.Ext(workdir))
	}
	results := map[string]string{}
	for _, svc := range project.Services {
		containerName := fmt.Sprintf("%s_%s", project.Name, svc.Name)
		recordKey := fmt.Sprintf("%s/%s", payload.Name, svc.Name)
		if svc.Image == "" {
			return nil, fmt.Errorf("compose service %s missing image reference", svc.Name)
		}
		if err := h.enforceImagePolicy(svc.Image); err != nil {
			return nil, err
		}
		expectedDigest := digestFromReference(svc.Image)
		ports, err := h.resolveServicePorts(payload.Name, svc.Name, svc.Ports)
		if err != nil {
			return nil, err
		}
		volumes := make([]dockerutil.VolumeBinding, 0, len(svc.Volumes))
		for _, vol := range svc.Volumes {
			if vol.Source == "" || vol.Target == "" {
				continue
			}
			sourceClean := filepath.Clean(vol.Source)
			if err := h.validateVolumeSource(sourceClean); err != nil {
				return nil, err
			}
			volumes = append(volumes, dockerutil.VolumeBinding{Source: sourceClean, Target: vol.Target})
		}
		env := map[string]string{}
		for k, v := range svc.Environment {
			if v != nil {
				env[k] = *v
			}
		}
		labels := dockerutil.WithAgentLabels(svc.Labels)
		labels["deploybot.job"] = payload.Name
		labels["deploybot.service"] = svc.Name
		labels["deploybot.image"] = svc.Image
		restart := payload.RestartPolicy
		res, err := h.deployContainerWithRollback(ctx, recordKey, containerName, svc.Image, expectedDigest, env, ports, volumes, labels, nil, restart)
		if err != nil {
			return nil, err
		}
		if m, ok := res.(map[string]string); ok {
			results[containerName] = m["container_id"]
		} else {
			results[containerName] = fmt.Sprintf("%v", res)
		}
	}
	return results, nil
}

func (h *Handler) deployDescriptor(ctx context.Context, workdir string, payload DeployJobPayload, selection strategySelection) (interface{}, error) {
	path := filepath.Join(workdir, selection.descriptor)
	descriptor, err := loadDeployDescriptor(path)
	if err != nil {
		return nil, err
	}
	image := descriptor.Image
	if image == "" {
		return nil, fmt.Errorf("deploy.json missing image")
	}
	if err := h.enforceImagePolicy(image); err != nil {
		return nil, err
	}
	expectedDigest := descriptor.ImageDigest
	if expectedDigest == "" {
		expectedDigest = payload.ImageDigest
	}
	ports, err := h.preparePorts(descriptor.Ports)
	if err != nil {
		return nil, err
	}
	volumes := make([]dockerutil.VolumeBinding, 0, len(descriptor.Volumes))
	for _, vol := range descriptor.Volumes {
		sourceClean := filepath.Clean(vol.Source)
		if err := h.validateVolumeSource(sourceClean); err != nil {
			return nil, err
		}
		volumes = append(volumes, dockerutil.VolumeBinding{Source: sourceClean, Target: vol.Target})
	}
	labels := dockerutil.WithAgentLabels(descriptor.Labels)
	labels["deploybot.job"] = payload.Name
	labels["deploybot.image"] = image
	containerName := descriptor.Name
	if containerName == "" {
		containerName = payload.Name
	}
	env := mergeEnv(payload.Environment, descriptor.Environment)
	health := descriptor.Health.toDocker()
	restart := descriptor.Restart
	if restart == "" {
		restart = payload.RestartPolicy
	}
	return h.deployContainerWithRollback(ctx, payload.Name, containerName, image, expectedDigest, env, ports, volumes, labels, health, restart)
}

func (h *Handler) deployDockerfile(ctx context.Context, workdir string, payload DeployJobPayload, selection strategySelection) (interface{}, error) {
	tagBase := sanitizeName(payload.Name)
	if tagBase == "" {
		tagBase = sanitizeName(filepath.Base(workdir))
	}
	imageTag := dockerutil.SanitizeTag("deploybot/" + tagBase)
	if err := h.buildImage(ctx, workdir, selection.dockerfile, imageTag); err != nil {
		return nil, err
	}
	expectedDigest := ""
	if h.securityEnabled() && h.Cfg.RequireImageDigest {
		digest, err := h.Docker.ImageDigest(ctx, imageTag)
		if err != nil {
			return nil, err
		}
		expectedDigest = digest
	}
	ports, err := h.preparePorts(payload.Ports)
	if err != nil {
		return nil, err
	}
	volumes := make([]dockerutil.VolumeBinding, 0, len(payload.Volumes))
	for _, vol := range payload.Volumes {
		sourceClean := filepath.Clean(vol.Source)
		if err := h.validateVolumeSource(sourceClean); err != nil {
			return nil, err
		}
		volumes = append(volumes, dockerutil.VolumeBinding{Source: sourceClean, Target: vol.Target})
	}
	labels := dockerutil.WithAgentLabels(map[string]string{"deploybot.job": payload.Name})
	labels["deploybot.image"] = imageTag
	health := payload.HealthCheck.toDocker()
	restart := payload.RestartPolicy
	if restart == "" {
		restart = "unless-stopped"
	}
	containerName := payload.Name
	if containerName == "" {
		containerName = sanitizeName(filepath.Base(workdir))
	}
	return h.deployContainerWithRollback(ctx, payload.Name, containerName, imageTag, expectedDigest, payload.Environment, ports, volumes, labels, health, restart)
}

func (h *Handler) deployImage(ctx context.Context, _ string, payload DeployJobPayload, selection strategySelection) (interface{}, error) {
	if err := h.enforceImagePolicy(selection.image); err != nil {
		return nil, err
	}
	expectedDigest := payload.ImageDigest
	if expectedDigest == "" {
		expectedDigest = digestFromReference(selection.image)
	}
	ports, err := h.preparePorts(payload.Ports)
	if err != nil {
		return nil, err
	}
	volumes := make([]dockerutil.VolumeBinding, 0, len(payload.Volumes))
	for _, vol := range payload.Volumes {
		sourceClean := filepath.Clean(vol.Source)
		if err := h.validateVolumeSource(sourceClean); err != nil {
			return nil, err
		}
		volumes = append(volumes, dockerutil.VolumeBinding{Source: sourceClean, Target: vol.Target})
	}
	labels := dockerutil.WithAgentLabels(map[string]string{"deploybot.job": payload.Name})
	labels["deploybot.image"] = selection.image
	health := payload.HealthCheck.toDocker()
	restart := payload.RestartPolicy
	if restart == "" {
		restart = "unless-stopped"
	}
	containerName := payload.Name
	if containerName == "" {
		containerName = sanitizeName(selection.image)
	}
	return h.deployContainerWithRollback(ctx, payload.Name, containerName, selection.image, expectedDigest, payload.Environment, ports, volumes, labels, health, restart)
}

func (h *Handler) deployContainerWithRollback(ctx context.Context, recordKey, containerName, image string, expectedDigest string, env map[string]string, ports []dockerutil.PortBinding, volumes []dockerutil.VolumeBinding, labels map[string]string, health *container.HealthConfig, restart string) (interface{}, error) {
	if err := h.enforceImagePolicy(image); err != nil {
		return nil, err
	}
	if err := h.verifyImageDigest(ctx, image, expectedDigest); err != nil {
		return nil, err
	}
	labels = dockerutil.WithAgentLabels(labels)
	labels["deploybot.container"] = containerName
	labels["deploybot.image"] = image
	prev, hasPrev := h.State.LastDeployment(recordKey)
	var prevRename string
	if hasPrev {
		prevRename = fmt.Sprintf("%s-previous-%d", containerName, time.Now().Unix())
		stopCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		defer cancel()
		_ = h.Docker.StopContainer(stopCtx, prev.ContainerID, nil)
		if err := h.Docker.RenameContainer(ctx, prev.ContainerID, prevRename); err != nil {
			return nil, err
		}
	}
	if restart == "" {
		restart = "unless-stopped"
	}
	id, err := h.Docker.DeploySingle(ctx, dockerutil.DeploySingleOptions{Name: containerName, Image: image, Environment: env, Ports: ports, Volumes: volumes, Labels: labels, Healthcheck: health, RestartPolicy: restart})
	if err != nil {
		if hasPrev {
			_ = h.recoverPrevious(ctx, prev.ContainerID, containerName)
		}
		return nil, err
	}
	if err := h.Docker.WaitHealthy(ctx, id, h.Cfg.HealthTimeout); err != nil {
		_ = h.Docker.StopContainer(ctx, id, nil)
		_ = h.Docker.RemoveContainer(ctx, id, true)
		if hasPrev {
			_ = h.recoverPrevious(ctx, prev.ContainerID, containerName)
		}
		return nil, err
	}
	if hasPrev {
		_ = h.Docker.RemoveContainer(ctx, prevRename, true)
	}
	record := state.DeploymentRecord{Name: containerName, ContainerID: id}
	_ = h.State.RecordDeployment(recordKey, record)
	return map[string]string{"container_id": id}, nil
}

func (h *Handler) recoverPrevious(ctx context.Context, id, desiredName string) error {
	_ = h.Docker.RenameContainer(ctx, id, desiredName)
	return h.Docker.StartContainer(ctx, id)
}

func (h *Handler) resolveServicePorts(jobName, serviceName string, ports []composetypes.ServicePortConfig) ([]dockerutil.PortBinding, error) {
	bindings := make([]dockerutil.PortBinding, 0, len(ports))
	for _, p := range ports {
		target := int(p.Target)
		published := 0
		if p.Published != "" {
			val, err := strconv.Atoi(p.Published)
			if err == nil {
				published = val
			}
		}
		if published == 0 {
			key := fmt.Sprintf("%s:%s:%d", jobName, serviceName, target)
			port, err := h.State.ReservePort(key, 0)
			if err != nil {
				return nil, err
			}
			published = port
		}
		proto := string(p.Protocol)
		bindings = append(bindings, dockerutil.PortBinding{ContainerPort: target, HostPort: published, Protocol: proto})
	}
	return bindings, nil
}

func (h *Handler) preparePorts(ports []PortMapping) ([]dockerutil.PortBinding, error) {
	bindings := make([]dockerutil.PortBinding, 0, len(ports))
	for _, p := range ports {
		target := p.Target
		if target == 0 {
			return nil, fmt.Errorf("port mapping missing target port")
		}
		published := 0
		if p.Published != "" && p.Published != "auto" {
			value, err := strconv.Atoi(p.Published)
			if err != nil {
				return nil, fmt.Errorf("invalid published port %q: %w", p.Published, err)
			}
			published = value
		}
		if published == 0 {
			key := p.Key
			if key == "" {
				key = fmt.Sprintf("auto:%d", target)
			}
			port, err := h.State.ReservePort(key, 0)
			if err != nil {
				return nil, err
			}
			published = port
		}
		bindings = append(bindings, dockerutil.PortBinding{ContainerPort: target, HostPort: published, Protocol: p.Protocol})
	}
	return bindings, nil
}

// compose health and restart mapping omitted for compatibility; rely on defaults/restart policy from payload

func fileExists(path string) bool { info, err := os.Stat(path); return err == nil && !info.IsDir() }

func mergeEnv(a, b map[string]string) map[string]string {
	res := map[string]string{}
	for k, v := range a {
		res[k] = v
	}
	for k, v := range b {
		res[k] = v
	}
	return res
}

func sanitizeName(name string) string {
	replaced := strings.ReplaceAll(name, " ", "-")
	replaced = strings.ToLower(replaced)
	return replaced
}

// deployDescriptor JSON structures.
type deployDescriptor struct {
	Name        string            `json:"name"`
	Image       string            `json:"image"`
	ImageDigest string            `json:"image_digest"`
	Environment map[string]string `json:"environment"`
	Volumes     []VolumeMapping   `json:"volumes"`
	Ports       []PortMapping     `json:"ports"`
	Restart     string            `json:"restart_policy"`
	Health      *DeployHealth     `json:"health"`
	Labels      map[string]string `json:"labels"`
}

type DeployHealth struct {
	Test     []string `json:"test"`
	Interval int      `json:"interval"`
	Timeout  int      `json:"timeout"`
	Retries  int      `json:"retries"`
}

func (d *DeployHealth) toDocker() *container.HealthConfig {
	if d == nil {
		return nil
	}
	interval := time.Duration(d.Interval)
	if interval == 0 {
		interval = 10
	}
	timeout := time.Duration(d.Timeout)
	if timeout == 0 {
		timeout = 5
	}
	return &container.HealthConfig{Test: d.Test, Interval: interval * time.Second, Timeout: timeout * time.Second, Retries: d.Retries}
}

func (h HealthCheckSpec) toDocker() *container.HealthConfig {
	if h.Type == "" {
		return nil
	}
	switch strings.ToLower(h.Type) {
	case "cmd", "cmd-shell":
		return &container.HealthConfig{Test: []string{"CMD-SHELL", h.Endpoint}}
	default:
		return nil
	}
}

func loadDeployDescriptor(path string) (*deployDescriptor, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	desc := &deployDescriptor{}
	if err := json.Unmarshal(data, desc); err != nil {
		return nil, err
	}
	return desc, nil
}

func (h *Handler) buildImage(ctx context.Context, contextDir, dockerfile, tag string) error {
	tar, err := dockerutil.CreateBuildContext(contextDir, dockerfile)
	if err != nil {
		return err
	}
	defer tar.Close()
	return h.Docker.BuildImage(ctx, tar, dockerfile, tag)
}
