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
	"strings"
	"time"

	"deploybot-agent/internal/audit"
	"deploybot-agent/internal/config"
	"deploybot-agent/internal/dockerutil"
	"deploybot-agent/internal/git"
	"deploybot-agent/internal/state"
)

// LogPublisher streams logs back to the controller.
type LogPublisher interface {
	Publish(ctx context.Context, jobID string, reader io.Reader) error
}

// Handler executes controller jobs.
type Handler struct {
	Cfg         config.Config
	State       *state.Store
	Docker      *dockerutil.Manager
	LogPublisher LogPublisher
	Audit        *audit.Logger
}

// Handle executes a job and returns optional detail for acknowledgements.
func (h *Handler) Handle(ctx context.Context, job *Job) (interface{}, error) {
	start := time.Now()
	h.audit("job.start", map[string]interface{}{"job_id": job.ID, "job_type": job.Type})

	var (
		result interface{}
		err    error
	)

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
	fields := map[string]interface{}{
		"job_id":      job.ID,
		"job_type":    job.Type,
		"duration_ms": duration.Milliseconds(),
	}
	if err != nil {
		status = "failed"
		fields["error"] = err.Error()
	}
	fields["status"] = status
	h.audit("job.finish", fields)

	return result, err
}

func (h *Handler) handleDeploy(ctx context.Context, jobID string, payload DeployJobPayload) (interface{}, error) {
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
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			return nil, err
		}
	}
	result := map[string]interface{}{
		"exit_code": exitCode,
		"stdout":    limitOutput(stdout.String()),
		"stderr":    limitOutput(stderr.String()),
	}
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

func (h *Handler) securityEnabled() bool {
	return !h.Cfg.SecurityBypass
}

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
