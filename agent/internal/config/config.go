package config

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config represents runtime configuration for the agent.
type Config struct {
	ControllerURL           string
	AgentToken              string
	HeartbeatInterval       time.Duration
	DataDir                 string
	WorkDir                 string
	HealthTimeout           time.Duration
	LogsFollowDuration      time.Duration
	AllowInsecureController bool
	ControllerCAFile        string
	ControllerCAPins        []string
	ClientCertFile          string
	ClientKeyFile           string
	SecurityBypass          bool
	EnableStateEncryption   bool
	EncryptionKey           string
	RegistryAllowList       []string
	RequireImageDigest      bool
	AllowedVolumeRoots      []string
	CleanupWorkspaces       bool
	AuditLogPath            string
	AllowUnsafeCommands     bool
	InteractiveSetup        bool
}

// Load parses CLI flags and environment variables into a Config.
func Load() (Config, error) {
	cfg := Config{}
	defaultHeartbeat := durationFromEnv("HEARTBEAT_INTERVAL", 10*time.Second)
	defaultHealth := durationFromEnv("HEALTH_TIMEOUT", 60*time.Second)
	defaultLogsDuration := durationFromEnv("LOGS_FOLLOW_DURATION", 2*time.Minute)
	flag.StringVar(&cfg.ControllerURL, "controller-url", os.Getenv("CONTROLLER_URL"), "DeployBot controller base URL")
	flag.StringVar(&cfg.AgentToken, "agent-token", os.Getenv("AGENT_TOKEN"), "DeployBot agent bootstrap token")
	flag.DurationVar(&cfg.HeartbeatInterval, "heartbeat-interval", defaultHeartbeat, "Heartbeat interval to controller")
	flag.StringVar(&cfg.DataDir, "data-dir", valueOr(os.Getenv("AGENT_DATA_DIR"), "/var/lib/deploybot"), "Persistent state directory")
	flag.StringVar(&cfg.WorkDir, "work-dir", os.Getenv("AGENT_WORK_DIR"), "Override git work directory; defaults to data-dir/work")
	flag.DurationVar(&cfg.HealthTimeout, "health-timeout", defaultHealth, "Maximum time to wait for healthy container")
	flag.DurationVar(&cfg.LogsFollowDuration, "logs-follow-duration", defaultLogsDuration, "Default duration to follow logs for log jobs")
	flag.BoolVar(&cfg.AllowInsecureController, "allow-insecure-controller", boolFromEnv("ALLOW_INSECURE_CONTROLLER", false), "Permit HTTP or insecure TLS for controller communication")
	flag.StringVar(&cfg.ControllerCAFile, "controller-ca", os.Getenv("CONTROLLER_CA_FILE"), "PEM bundle used to trust the controller")
	defaultPins := listFromEnv("CONTROLLER_CA_PINS")
	flag.Func("controller-ca-pins", "Comma-separated SHA256 fingerprints for pinning controller certificates", func(val string) error {
		if val == "" {
			cfg.ControllerCAPins = nil
			return nil
		}
		cfg.ControllerCAPins = strings.Split(val, ",")
		return nil
	})
	if cfg.ControllerCAPins == nil {
		cfg.ControllerCAPins = defaultPins
	}
	flag.StringVar(&cfg.ClientCertFile, "client-cert", os.Getenv("CLIENT_CERT_FILE"), "Client certificate for mutual TLS")
	flag.StringVar(&cfg.ClientKeyFile, "client-key", os.Getenv("CLIENT_KEY_FILE"), "Client key for mutual TLS")
	flag.BoolVar(&cfg.SecurityBypass, "security-bypass", boolFromEnv("SECURITY_BYPASS", false), "Disable security enforcement (not recommended)")
	flag.BoolVar(&cfg.EnableStateEncryption, "state-encryption", boolFromEnv("STATE_ENCRYPTION", os.Getenv("AGENT_STATE_KEY") != ""), "Encrypt credentials in state file")
	flag.StringVar(&cfg.EncryptionKey, "encryption-key", os.Getenv("AGENT_STATE_KEY"), "Key material for state encryption")
	defaultRegistries := listFromEnv("REGISTRY_ALLOWLIST")
	flag.Func("registry-allowlist", "Comma separated list of registries permitted for deployments", func(val string) error {
		if val == "" {
			cfg.RegistryAllowList = nil
			return nil
		}
		cfg.RegistryAllowList = strings.Split(val, ",")
		return nil
	})
	if cfg.RegistryAllowList == nil {
		cfg.RegistryAllowList = defaultRegistries
	}
	flag.BoolVar(&cfg.RequireImageDigest, "require-image-digest", boolFromEnv("REQUIRE_IMAGE_DIGEST", false), "Reject images that are not pinned by digest")
	defaultVolumeRoots := listFromEnv("ALLOWED_VOLUME_ROOTS")
	flag.Func("allowed-volume-roots", "Comma separated host paths that volume mounts must fall under", func(val string) error {
		if val == "" {
			cfg.AllowedVolumeRoots = nil
			return nil
		}
		cfg.AllowedVolumeRoots = strings.Split(val, ",")
		return nil
	})
	if cfg.AllowedVolumeRoots == nil {
		cfg.AllowedVolumeRoots = defaultVolumeRoots
	}
	flag.BoolVar(&cfg.CleanupWorkspaces, "cleanup-workspaces", boolFromEnv("CLEANUP_WORKSPACES", true), "Remove git workspaces after jobs complete")
	flag.StringVar(&cfg.AuditLogPath, "audit-log", os.Getenv("AUDIT_LOG_PATH"), "File path for JSONL audit logs")
	flag.BoolVar(&cfg.AllowUnsafeCommands, "allow-unsafe-commands", boolFromEnv("ALLOW_UNSAFE_COMMANDS", false), "Permit exec/env jobs that run host commands")
	flag.BoolVar(&cfg.InteractiveSetup, "interactive-setup", boolFromEnv("AGENT_INTERACTIVE_SETUP", true), "Run interactive prerequisite checks before starting")
	flag.Parse()
	if cfg.ControllerURL == "" {
		return Config{}, errors.New("controller URL is required")
	}
	if cfg.AgentToken == "" {
		return Config{}, errors.New("agent token is required")
	}
	if cfg.WorkDir == "" {
		cfg.WorkDir = fmt.Sprintf("%s/work", cfg.DataDir)
	}
	return cfg, nil
}

func durationFromEnv(key string, fallback time.Duration) time.Duration {
	val := os.Getenv(key)
	if val == "" {
		return fallback
	}
	n, err := strconv.Atoi(val)
	if err != nil {
		return fallback
	}
	return time.Duration(n) * time.Second
}
func valueOr(v, fallback string) string {
	if v == "" {
		return fallback
	}
	return v
}
func boolFromEnv(key string, def bool) bool {
	val := os.Getenv(key)
	if val == "" {
		return def
	}
	b, err := strconv.ParseBool(val)
	if err != nil {
		return def
	}
	return b
}
func listFromEnv(key string) []string {
	val := strings.TrimSpace(os.Getenv(key))
	if val == "" {
		return nil
	}
	parts := strings.Split(val, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		trimmed := strings.TrimSpace(p)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}
