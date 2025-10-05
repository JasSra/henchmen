package git

import (
	"context"
	"fmt"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
)

var invalidNameChars = regexp.MustCompile(`[^a-zA-Z0-9._-]+`)

// WorkspacePath returns a deterministic workspace path inside baseDir.
func WorkspacePath(baseDir, repoURL, ref string) string {
	repo := repoURL
	if idx := strings.LastIndex(repo, "/"); idx >= 0 {
		repo = repo[idx+1:]
	}
	repo = strings.TrimSuffix(repo, ".git")
	repo = invalidNameChars.ReplaceAllString(repo, "-")
	refSafe := invalidNameChars.ReplaceAllString(ref, "-")
	ts := time.Now().UTC().Format("20060102T150405Z")
	return filepath.Join(baseDir, repo, refSafe, ts)
}

// ShallowClone clones repository@ref into dest with shallow depth 1.
func ShallowClone(ctx context.Context, repoURL, ref, dest string) error {
	opts := &git.CloneOptions{
		URL:           repoURL,
		Depth:         1,
		SingleBranch:  true,
		ReferenceName: plumbing.ReferenceName(refFromInput(ref)),
	}
	if hash := tryParseHash(ref); hash != nil {
		opts.ReferenceName = ""
		opts.SingleBranch = false
		opts.Depth = 0
		opts.Tags = git.NoTags
		opts.NoCheckout = false
		// go-git doesn't support direct hash checkout on clone; fallback to cloning default branch then checkout.
	}

	repo, err := git.PlainCloneContext(ctx, dest, false, opts)
	if err != nil {
		return fmt.Errorf("clone failed: %w", err)
	}

	if hash := tryParseHash(ref); hash != nil {
		w, err := repo.Worktree()
		if err != nil {
			return err
		}
		if err := w.Checkout(&git.CheckoutOptions{Hash: *hash}); err != nil {
			return err
		}
	}
	return nil
}

func refFromInput(ref string) string {
	if ref == "" {
		return plumbing.HEAD.String()
	}
	if strings.HasPrefix(ref, "refs/") {
		return ref
	}
	// assume branch name
	return fmt.Sprintf("refs/heads/%s", ref)
}

func tryParseHash(ref string) *plumbing.Hash {
	if len(ref) != 40 {
		return nil
	}
	for _, r := range ref {
		if (r >= '0' && r <= '9') || (r >= 'a' && r <= 'f') || (r >= 'A' && r <= 'F') {
			continue
		}
		return nil
	}
	h := plumbing.NewHash(ref)
	return &h
}

// VerifyHEAD validates that the workspace HEAD matches the expected commit.
func VerifyHEAD(workdir, expected string) error {
	if expected == "" {
		return nil
	}
	repo, err := git.PlainOpen(workdir)
	if err != nil {
		return err
	}
	head, err := repo.Head()
	if err != nil {
		return err
	}
	actual := head.Hash().String()
	if !strings.EqualFold(actual, expected) {
		if !strings.HasPrefix(actual, expected) {
			return fmt.Errorf("repository HEAD %s does not match expected %s", actual, expected)
		}
	}
	return nil
}
