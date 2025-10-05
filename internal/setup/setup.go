package setup

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"strings"

	"deploybot-agent/internal/config"
)

const serviceUser = "deploybot"

var reader = bufio.NewReader(os.Stdin)

// Run performs interactive host checks before the agent starts.
func Run(cfg config.Config) error {
	fmt.Println("== DeployBot Agent Interactive Setup ==")
	fmt.Println("We'll verify host prerequisites before launching the agent.\n")

	if err := ensureServiceAccount(cfg); err != nil {
		return err
	}
	if err := ensureDockerMembership(); err != nil {
		return err
	}
	if err := ensureTLSMaterials(cfg); err != nil {
		return err
	}

	fmt.Println("\nSetup checks complete. Continuing with agent startup...\n")
	return nil
}

func ensureServiceAccount(cfg config.Config) error {
	_, err := user.Lookup(serviceUser)
	if err == nil {
		fmt.Printf("✔ Service account '%s' is present.\n", serviceUser)
		return nil
	}
	if _, ok := err.(user.UnknownUserError); !ok {
		return err
	}

	fmt.Printf("⚠ Service account '%s' was not found.\n", serviceUser)
	if os.Geteuid() != 0 {
		fmt.Printf("   Run as root: useradd --system --create-home --home-dir %s --shell /usr/sbin/nologin %s\n", cfg.DataDir, serviceUser)
		return nil
	}

	if !promptYesNo(fmt.Sprintf("Create the '%s' service account now?", serviceUser), true) {
		return nil
	}

	args := []string{"--system", "--create-home", "--home-dir", cfg.DataDir, "--shell", "/usr/sbin/nologin", serviceUser}
	cmd := exec.Command("useradd", args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		if errors.Is(err, exec.ErrNotFound) {
			fmt.Println("✖ 'useradd' command not found. Create the account manually using your platform's tooling.")
			return nil
		}
		fmt.Printf("✖ Failed to create service account automatically: %v\n", err)
		fmt.Printf("   Run manually: useradd --system --create-home --home-dir %s --shell /usr/sbin/nologin %s\n", cfg.DataDir, serviceUser)
		return nil
	}
	fmt.Println("✔ Created service account and home directory.")
	return nil
}

func ensureDockerMembership() error {
	if _, err := user.LookupGroup("docker"); err != nil {
		fmt.Println("⚠ Docker group not found. Ensure Docker is installed and the 'docker' group exists.")
		return nil
	}

	inGroup, err := userInGroup(serviceUser, "docker")
	if err != nil {
		return err
	}
	if inGroup {
		fmt.Println("✔ Service account already belongs to the 'docker' group.")
		return nil
	}

	fmt.Println("⚠ Service account is not part of the 'docker' group.")
	if os.Geteuid() != 0 {
		fmt.Println("   Run: sudo usermod -aG docker deploybot")
		return nil
	}
	if !promptYesNo("Add deploybot to the docker group now?", true) {
		return nil
	}
	cmd := exec.Command("usermod", "-aG", "docker", serviceUser)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		if errors.Is(err, exec.ErrNotFound) {
			fmt.Println("✖ 'usermod' command not found. Add the account to the docker group manually.")
			return nil
		}
		fmt.Printf("✖ Failed to add user to docker group automatically: %v\n", err)
		fmt.Println("   Run manually: usermod -aG docker deploybot")
		return nil
	}
	fmt.Println("✔ Added deploybot to the docker group.")
	return nil
}

func ensureTLSMaterials(cfg config.Config) error {
	if err := ensureTLSFile(cfg.ControllerCAFile, "controller CA bundle", 0o644); err != nil {
		return err
	}
	if err := ensureTLSFile(cfg.ClientCertFile, "client certificate", 0o644); err != nil {
		return err
	}
	if err := ensureTLSFile(cfg.ClientKeyFile, "client key", 0o600); err != nil {
		return err
	}
	if len(cfg.ControllerCAPins) == 0 && cfg.ControllerCAFile == "" {
		fmt.Println("ℹ TIP: Configure CONTROLLER_CA_PINS or CONTROLLER_CA_FILE to pin the controller certificate in production.")
	}
	return nil
}

func ensureTLSFile(path, description string, mode os.FileMode) error {
	if path == "" {
		return nil
	}
	if _, err := os.Stat(path); err == nil {
		fmt.Printf("✔ %s found at %s.\n", description, path)
		return nil
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}

	fmt.Printf("⚠ %s missing at %s.\n", description, path)
	if os.Geteuid() != 0 {
		fmt.Printf("   Please create the file and populate it with the appropriate material.\n")
		return nil
	}
	if !promptYesNo(fmt.Sprintf("Create an empty placeholder for the %s now?", description), false) {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(path, []byte{}, mode); err != nil {
		fmt.Printf("✖ Failed to create placeholder: %v\n", err)
		return err
	}
	fmt.Printf("✔ Created placeholder %s. Populate it with real material before production use.\n", path)
	return nil
}

func userInGroup(username, group string) (bool, error) {
	data, err := os.ReadFile("/etc/group")
	if err != nil {
		return false, err
	}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Split(line, ":")
		if len(parts) < 4 {
			continue
		}
		if parts[0] != group {
			continue
		}
		members := strings.Split(parts[3], ",")
		for _, member := range members {
			if strings.TrimSpace(member) == username {
				return true, nil
			}
		}
		return false, nil
	}
	return false, nil
}

func promptYesNo(question string, defaultYes bool) bool {
	indicator := "Y/n"
	if !defaultYes {
		indicator = "y/N"
	}
	for {
		fmt.Printf("%s [%s]: ", question, indicator)
		input, err := reader.ReadString('\n')
		if err != nil {
			return defaultYes
		}
		input = strings.TrimSpace(strings.ToLower(input))
		if input == "" {
			return defaultYes
		}
		if input == "y" || input == "yes" {
			return true
		}
		if input == "n" || input == "no" {
			return false
		}
		fmt.Println("Please enter 'y' or 'n'.")
	}
}
