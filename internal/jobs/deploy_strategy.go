package jobs

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"deploybot-agent/internal/dockerutil"
	"deploybot-agent/internal/state"

	"github.com/compose-spec/compose-go/loader"
	"github.com/compose-spec/compose-go/types"
	"github.com/docker/docker/api/types/container"
)

type strategyKind int

const (
	strategyCompose strategyKind = iota
	strategyDeployJSON
	strategyDockerfile
	strategyImage
)

type strategySelection struct {
	kind          strategyKind
	composeFile   string
	descriptor    string
	dockerfile    string
	image         string
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
	opts := loader.Options{
		WorkingDir: workdir,
		ProjectName: payload.ComposeProject,
		ConfigFiles: []types.ConfigFile{{Filename: selection.composeFile}},
	}
	project, err := loader.Load(opts)
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
			env[k] = v
		}

		health := composeHealthToDocker(svc.HealthCheck)

		labels := svc.Labels
		if labels == nil {
			labels = map[string]string{}
		}
		labels["deploybot.job"] = payload.Name
		labels["deploybot.service"] = svc.Name

	restart := composeRestartToDocker(svc.Deploy)
	if restart == "" {
		restart = payload.RestartPolicy
	}

		id, err := h.deployContainerWithRollback(ctx, recordKey, containerName, svc.Image, expectedDigest, env, ports, volumes, labels, health, restart)
		if err != nil {
			return nil, err
		}
		results[containerName] = id
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

	labels := descriptor.Labels
	if labels == nil {
		labels = map[string]string{}
	}
	labels["deploybot.job"] = payload.Name

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

	labels := map[string]string{"deploybot.job": payload.Name}

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
	labels := map[string]string{"deploybot.job": payload.Name}

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
	if labels == nil {
		labels = map[string]string{}
	}
	labels["deploybot.container"] = containerName

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

	id, err := h.Docker.DeploySingle(ctx, dockerutil.DeploySingleOptions{
		Name:        containerName,
		Image:       image,
		Environment: env,
		Ports:       ports,
		Volumes:     volumes,
		Labels:      labels,
		Healthcheck: health,
		RestartPolicy: restart,
	})
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

func (h *Handler) resolveServicePorts(jobName, serviceName string, ports []types.ServicePortConfig) ([]dockerutil.PortBinding, error) {
	bindings := make([]dockerutil.PortBinding, 0, len(ports))
	for _, p := range ports {
		target := int(p.Target)
		published := int(p.Published)
		if published == 0 {
			key := fmt.Sprintf("%s:%s:%d", jobName, serviceName, target)
			port, err := h.State.ReservePort(key, 0)
			if err != nil {
				return nil, err
			}
			published = port
		}
		bindings = append(bindings, dockerutil.PortBinding{ContainerPort: target, HostPort: published, Protocol: string(p.Protocol)})
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

func composeHealthToDocker(health *types.HealthCheckConfig) *container.HealthConfig {
	if health == nil {
		return nil
	}
	return &container.HealthConfig{
		Test:        health.Test,
		Interval:    durationFromPtr(health.Interval, time.Second*10),
		Timeout:     durationFromPtr(health.Timeout, time.Second*5),
		Retries:     health.Retries,
		StartPeriod: durationFromPtr(health.StartPeriod, time.Second*5),
	}
}

func composeRestartToDocker(deploy *types.DeployConfig) string {
	if deploy == nil || deploy.RestartPolicy == nil {
		return ""
	}
	switch deploy.RestartPolicy.Condition {
	case types.RestartPolicyConditionAny:
		return "unless-stopped"
	case types.RestartPolicyConditionOnFailure:
		return "on-failure"
	case types.RestartPolicyConditionNone:
		return "no"
	default:
		return ""
	}
}

func durationFromPtr(d *types.Duration, fallback time.Duration) time.Duration {
	if d == nil {
		return fallback
	}
	return d.Duration
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

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
	Name       string                       `json:"name"`
	Image      string                       `json:"image"`
	ImageDigest string                      `json:"image_digest"`
	Environment map[string]string           `json:"environment"`
	Volumes    []VolumeMapping              `json:"volumes"`
	Ports      []PortMapping                `json:"ports"`
	Restart    string                       `json:"restart_policy"`
	Health     *DeployHealth                `json:"health"`
	Labels     map[string]string            `json:"labels"`
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
	return &container.HealthConfig{
		Test:     d.Test,
		Interval: interval * time.Second,
		Timeout:  timeout * time.Second,
		Retries:  d.Retries,
	}
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
