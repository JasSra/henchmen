package dockerutil

import (
	"context"
	"io"
	"path/filepath"
	"strings"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/pkg/archive"
)

// CreateBuildContext builds a tarball for Docker image builds.
func CreateBuildContext(contextDir, dockerfile string) (io.ReadCloser, error) {
	if contextDir == "" {
		contextDir = "."
	}
	options := &archive.TarOptions{IncludeFiles: []string{"."}}
	return archive.TarWithOptions(contextDir, options)
}

// BuildImage builds a Docker image from the supplied context and dockerfile.
func (m *Manager) BuildImage(ctx context.Context, buildCtx io.ReadCloser, dockerfile, tag string) error {
	defer buildCtx.Close()
	tag = EnsureAgentImageTag(tag)
	ops := types.ImageBuildOptions{
		Dockerfile: filepath.ToSlash(dockerfile),
		Tags:       []string{tag},
		Labels:     DefaultImageLabels(),
		Remove:     true,
	}
	response, err := m.cli.ImageBuild(ctx, buildCtx, opts)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, response.Body)
	return nil
}

// SanitizeTag returns a docker-friendly tag name.
func SanitizeTag(base string) string {
	safe := strings.ToLower(base)
	safe = strings.ReplaceAll(safe, " ", "-")
	safe = strings.ReplaceAll(safe, ":", "-")
	return safe + ":" + time.Now().UTC().Format("20060102T150405")
}
