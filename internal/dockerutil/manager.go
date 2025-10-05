package dockerutil

import (
	"context"
	"fmt"
	"io"
	"strings"

	"deploybot-agent/internal/controller"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/client"
)

// Manager wraps the Docker SDK operations needed by the agent.
type Manager struct {
	cli *client.Client
}

// NewManager initialises the Docker client using environment configuration.
func NewManager() (*Manager, error) {
	cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, err
	}
	return &Manager{cli: cli}, nil
}

// Close releases resources associated with the Docker client.
func (m *Manager) Close() error {
	return m.cli.Close()
}

// Version returns the Docker engine version.
func (m *Manager) Version(ctx context.Context) (string, error) {
	ver, err := m.cli.ServerVersion(ctx)
	if err != nil {
		return "", err
	}
	return ver.Version, nil
}

// Inventory fetches metadata about running containers for heartbeat payloads.
func (m *Manager) Inventory(ctx context.Context) ([]controller.InventoryResource, error) {
	containers, err := m.cli.ContainerList(ctx, types.ContainerListOptions{All: true})
	if err != nil {
		return nil, err
	}

	resources := make([]controller.InventoryResource, 0, len(containers))
	for _, c := range containers {
		ports := map[string]string{}
		for _, port := range c.Ports {
			key := fmt.Sprintf("%s/%s", port.PrivatePort, port.Type)
			ports[key] = fmt.Sprintf("%s:%d", port.IP, port.PublicPort)
		}

		health := ""
		if c.State == "running" {
			ins, err := m.cli.ContainerInspect(ctx, c.ID)
			if err == nil && ins.State != nil && ins.State.Health != nil {
				health = ins.State.Health.Status
			}
		}

		resources = append(resources, controller.InventoryResource{
			Name:   trimLeadingSlash(c.Names),
			Image:  c.Image,
			Ports:  ports,
			Status: c.Status,
			Health: health,
		})
	}
	return resources, nil
}

// Restart restarts a container by name or ID.
func (m *Manager) Restart(ctx context.Context, name string) error {
	return m.cli.ContainerRestart(ctx, name, nil)
}

// Stop stops a container by name or ID.
func (m *Manager) Stop(ctx context.Context, name string) error {
	timeout := container.StopOptions{Timeout: nil}
	return m.cli.ContainerStop(ctx, name, timeout)
}

// Remove removes a container by name or ID.
func (m *Manager) Remove(ctx context.Context, name string, volumes bool) error {
	return m.cli.ContainerRemove(ctx, name, types.ContainerRemoveOptions{Force: true, RemoveVolumes: volumes})
}

// Logs returns a reader for streaming logs.
func (m *Manager) Logs(ctx context.Context, containerName string, tail int, follow bool) (io.ReadCloser, error) {
	options := types.ContainerLogsOptions{ShowStdout: true, ShowStderr: true, Follow: follow, Tail: fmt.Sprintf("%d", tail)}
	return m.cli.ContainerLogs(ctx, containerName, options)
}

// FindContainerByLabel locates container IDs by label.
func (m *Manager) FindContainerByLabel(ctx context.Context, key, value string) ([]types.Container, error) {
	args := filters.NewArgs(filters.Arg("label", fmt.Sprintf("%s=%s", key, value)))
	return m.cli.ContainerList(ctx, types.ContainerListOptions{All: true, Filters: args})
}

func trimLeadingSlash(names []string) string {
	if len(names) == 0 {
		return ""
	}
	name := names[0]
	for len(name) > 0 && name[0] == '/' {
		name = name[1:]
	}
	return name
}

// ImageDigest resolves the digest associated with an image reference.
func (m *Manager) ImageDigest(ctx context.Context, ref string) (string, error) {
	inspect, _, err := m.cli.ImageInspectWithRaw(ctx, ref)
	if err != nil {
		return "", err
	}
	if len(inspect.RepoDigests) > 0 {
		digest := inspect.RepoDigests[0]
		if idx := strings.Index(digest, "@"); idx >= 0 {
			return digest[idx+1:], nil
		}
		return digest, nil
	}
	return inspect.ID, nil
}
