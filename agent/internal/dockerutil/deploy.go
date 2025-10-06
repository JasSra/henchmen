package dockerutil

import (
	"context"
	"fmt"
	"io"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	imagetypes "github.com/docker/docker/api/types/image"
	"github.com/docker/docker/api/types/mount"
	"github.com/docker/docker/api/types/network"
	"github.com/docker/docker/client"
	"github.com/docker/go-connections/nat"
)

// PortBinding maps container ports to host ports.
type PortBinding struct {
	ContainerPort int
	HostPort      int
	Protocol      string
}

// VolumeBinding binds host paths into the container.
type VolumeBinding struct {
	Source string
	Target string
}

// DeploySingleOptions bundles container deployment inputs.
type DeploySingleOptions struct {
	Name          string
	Image         string
	Environment   map[string]string
	Ports         []PortBinding
	Volumes       []VolumeBinding
	RestartPolicy string
	Labels        map[string]string
	Healthcheck   *container.HealthConfig
	Network       string
}

// DeploySingle creates (or replaces) a single container according to options.
func (m *Manager) DeploySingle(ctx context.Context, opts DeploySingleOptions) (string, error) {
	if opts.RestartPolicy == "" {
		opts.RestartPolicy = "unless-stopped"
	}
	if err := m.EnsureImage(ctx, opts.Image); err != nil {
		return "", err
	}

	networking := &network.NetworkingConfig{}
	if opts.Network != "" {
		networking.EndpointsConfig = map[string]*network.EndpointSettings{opts.Network: {}}
	}

	ops.Labels = WithAgentLabels(opts.Labels)

	containerConfig := &container.Config{Image: opts.Image, Env: mapToEnv(opts.Environment), Labels: opts.Labels, Healthcheck: opts.Healthcheck}
	hostConfig := &container.HostConfig{RestartPolicy: container.RestartPolicy{Name: container.RestartPolicyMode(opts.RestartPolicy)}}

	if len(opts.Volumes) > 0 {
		hostConfig.Mounts = make([]mount.Mount, 0, len(opts.Volumes))
		for _, v := range opts.Volumes {
			hostConfig.Mounts = append(hostConfig.Mounts, mount.Mount{Type: mount.TypeBind, Source: v.Source, Target: v.Target})
		}
	}

	if len(opts.Ports) > 0 {
		bindings := nat.PortMap{}
		exposed := nat.PortSet{}
		for _, p := range opts.Ports {
			proto := p.Protocol
			if proto == "" {
				proto = "tcp"
			}
			port, err := nat.NewPort(proto, fmt.Sprintf("%d", p.ContainerPort))
			if err != nil {
				return "", err
			}
			exposed[port] = struct{}{}
			bindings[port] = []nat.PortBinding{{HostPort: fmt.Sprintf("%d", p.HostPort)}}
		}
		containerConfig.ExposedPorts = exposed
		hostConfig.PortBindings = bindings
	}

	resp, err := m.cli.ContainerCreate(ctx, containerConfig, hostConfig, networking, nil, opts.Name)
	if err != nil {
		return "", err
	}
	if err := m.cli.ContainerStart(ctx, resp.ID, container.StartOptions{}); err != nil {
		return "", err
	}
	return resp.ID, nil
}

// WaitHealthy waits for container health until timeout.
func (m *Manager) WaitHealthy(ctx context.Context, containerID string, timeout time.Duration) error {
	dl := time.Now().Add(timeout)
	for time.Now().Before(dl) {
		ins, err := m.cli.ContainerInspect(ctx, containerID)
		if err != nil {
			return err
		}
		if ins.State == nil {
			return fmt.Errorf("container has no state information")
		}
		if ins.State.Health == nil {
			if ins.State.Running {
				return nil
			}
		} else {
			sw := ins.State.Health.Status
			switch sw {
			case "starting":
			case "healthy":
				return nil
			case "unhealthy":
				return fmt.Errorf("container %s reported unhealthy", containerID)
			}
		}
		time.Sleep(2 * time.Second)
	}
	return fmt.Errorf("container %s did not become healthy within timeout", containerID)
}

func (m *Manager) EnsureImage(ctx context.Context, image string) error {
	_, _, err := m.cli.ImageInspectWithRaw(ctx, image)
	if err == nil {
		return nil
	}
	if client.IsErrNotFound(err) {
		reader, pullErr := m.cli.ImagePull(ctx, image, imagetypes.PullOptions{})
		if pullErr != nil {
			return pullErr
		}
		defer reader.Close()
		_, _ = io.Copy(io.Discard, reader)
		return nil
	}
	return err
}

func mapToEnv(env map[string]string) []string {
	if len(env) == 0 {
		return nil
	}
	out := make([]string, 0, len(env))
	for k, v := range env {
		out = append(out, fmt.Sprintf("%s=%s", k, v))
	}
	return out
}

// RemoveContainer removes container by ID.
func (m *Manager) RemoveContainer(ctx context.Context, id string, force bool) error {
	return m.cli.ContainerRemove(ctx, id, container.RemoveOptions{Force: force, RemoveVolumes: true})
}

// RenameContainer renames a container.
func (m *Manager) RenameContainer(ctx context.Context, id, newName string) error {
	return m.cli.ContainerRename(ctx, id, newName)
}

// StopContainer stops a container with timeout.
func (m *Manager) StopContainer(ctx context.Context, id string, timeout *time.Duration) error {
	var seconds *int
	if timeout != nil {
		s := int(timeout.Seconds())
		seconds = &s
	}
	return m.cli.ContainerStop(ctx, id, container.StopOptions{Timeout: seconds})
}

// StartContainer starts a stopped container.
func (m *Manager) StartContainer(ctx context.Context, id string) error {
	return m.cli.ContainerStart(ctx, id, container.StartOptions{})
}

// InspectContainer returns container inspect data.
func (m *Manager) InspectContainer(ctx context.Context, id string) (*types.ContainerJSON, error) {
	ins, err := m.cli.ContainerInspect(ctx, id)
	if err != nil {
		return nil, err
	}
	return &ins, nil
}

// CopyToContainer uploads content into container path.
func (m *Manager) CopyToContainer(ctx context.Context, id, path string, content io.Reader) error {
	return m.cli.CopyToContainer(ctx, id, path, content, types.CopyToContainerOptions{})
}
