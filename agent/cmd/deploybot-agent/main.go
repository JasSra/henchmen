package main

import (
	"context"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"deploybot-agent/internal/audit"
	"deploybot-agent/internal/config"
	"deploybot-agent/internal/controller"
	"deploybot-agent/internal/dockerutil"
	"deploybot-agent/internal/jobs"
	"deploybot-agent/internal/metrics"
	"deploybot-agent/internal/setup"
	"deploybot-agent/internal/state"

	"golang.org/x/term"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("config error: %v", err)
	}

	if err := os.MkdirAll(cfg.DataDir, 0o755); err != nil {
		log.Fatalf("failed to create data dir: %v", err)
	}
	if err := os.MkdirAll(cfg.WorkDir, 0o755); err != nil {
		log.Fatalf("failed to create work dir: %v", err)
	}

	if shouldRunInteractiveSetup(cfg) {
		if err := setup.Run(cfg); err != nil {
			log.Fatalf("interactive setup failed: %v", err)
		}
	}

	statePath := filepath.Join(cfg.DataDir, "agent.json")
	var cipher state.Cipher
	storeOpts := []state.Option{}
	if cfg.EncryptionKey != "" {
		cipher, err = state.NewAESCipher(cfg.EncryptionKey)
		if err != nil {
			log.Fatalf("state encryption setup failed: %v", err)
		}
		storeOpts = append(storeOpts, state.WithCipher(cipher))
	} else if cfg.EnableStateEncryption && !cfg.SecurityBypass {
		log.Fatalf("state encryption enabled but no AGENT_STATE_KEY provided")
	}
	if cipher != nil {
		storeOpts = append(storeOpts, state.WithTokenEncryption(cfg.EnableStateEncryption && !cfg.SecurityBypass))
	}
	store, err := state.Open(statePath, storeOpts...)
	if err != nil {
		log.Fatalf("state open error: %v", err)
	}

	agentID, storedToken, err := store.AgentCredentials()
	if err != nil {
		log.Fatalf("state credential error: %v", err)
	}
	token := storedToken
	if token == "" {
		token = cfg.AgentToken
	}

	controllerOpts := []controller.Option{}
	controllerOpts = append(controllerOpts, controller.WithTLSConfig(controller.TLSConfig{
		AllowInsecure: cfg.AllowInsecureController || cfg.SecurityBypass,
		CAFile:        cfg.ControllerCAFile,
		CAPins:        cfg.ControllerCAPins,
		ClientCert:    cfg.ClientCertFile,
		ClientKey:     cfg.ClientKeyFile,
	}))
	if cfg.SecurityBypass {
		controllerOpts = append(controllerOpts, controller.WithSecurityBypass())
	}
	client, err := controller.New(cfg.ControllerURL, token, controllerOpts...)
	if err != nil {
		log.Fatalf("controller client error: %v", err)
	}

	dockerManager, err := dockerutil.NewManager()
	if err != nil {
		log.Fatalf("docker init error: %v", err)
	}
	defer dockerManager.Close()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	hostname, _ := os.Hostname()

	capabilities := buildCapabilities(cfg)
	auditLogger, err := audit.NewLogger(cfg.AuditLogPath)
	if err != nil {
		log.Fatalf("failed to initialise audit logger: %v", err)
	}

	if agentID == "" || storedToken == "" {
		if err := bootstrapAgent(ctx, cfg, store, client, dockerManager, hostname, capabilities); err != nil {
			log.Fatalf("registration failed: %v", err)
		}
		agentID, token, err = store.AgentCredentials()
		if err != nil {
			log.Fatalf("state credential error: %v", err)
		}
	}

	publisher := &controllerLogPublisher{client: client, agentID: agentID}
	handler := &jobs.Handler{Cfg: cfg, State: store, Docker: dockerManager, LogPublisher: publisher, Audit: auditLogger}

	ticker := time.NewTicker(cfg.HeartbeatInterval)
	defer ticker.Stop()

	log.Printf("agent %s running; heartbeat every %s", agentID, cfg.HeartbeatInterval)

	for {
		select {
		case <-ctx.Done():
			log.Printf("shutdown requested: %v", ctx.Err())
			return
		case <-ticker.C:
			if err := sendHeartbeat(ctx, handler, client, dockerManager, agentID, capabilities); err != nil {
				log.Printf("heartbeat error: %v", err)
			}
		}
	}
}

func bootstrapAgent(ctx context.Context, cfg config.Config, store *state.Store, client *controller.Client, dockerManager *dockerutil.Manager, hostname string, capabilities []string) error {
	snap, err := metrics.Collect(ctx)
	if err != nil {
		return err
	}

	dockerVersion, err := dockerManager.Version(ctx)
	if err != nil {
		return err
	}

	req := controller.RegisterRequest{
		Token: cfg.AgentToken,
		Metrics: controller.Metrics{
			CPUPercent: snap.CPUPercent,
			MemPercent: snap.MemPercent,
			DiskFreeGB: snap.DiskFreeGB,
		},
		DockerVersion: dockerVersion,
		Hostname:      hostname,
		Capabilities:  capabilities,
	}

	resp, err := client.Register(ctx, req)
	if err != nil {
		return err
	}

	return store.SetAgent(resp.AgentID, resp.AgentToken)
}

func sendHeartbeat(ctx context.Context, handler *jobs.Handler, client *controller.Client, dockerManager *dockerutil.Manager, agentID string, capabilities []string) error {
	hbCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()

	snap, err := metrics.Collect(hbCtx)
	if err != nil {
		return fmt.Errorf("collect metrics: %w", err)
	}

	inventory, err := dockerManager.Inventory(hbCtx)
	if err != nil {
		return fmt.Errorf("inventory: %w", err)
	}

	req := controller.HeartbeatRequest{
		Metrics: controller.Metrics{
			CPUPercent: snap.CPUPercent,
			MemPercent: snap.MemPercent,
			DiskFreeGB: snap.DiskFreeGB,
		},
		Inventory: inventory,
		Capabilities: capabilities,
	}

	resp, err := client.Heartbeat(hbCtx, agentID, req)
	if err != nil {
		return fmt.Errorf("controller heartbeat: %w", err)
	}

	if resp.Job == nil {
		return nil
	}

	jobCtx, cancelJob := context.WithTimeout(ctx, 10*time.Minute)
	defer cancelJob()

	log.Printf("received job %s (%s)", resp.Job.ID, resp.Job.Type)
	// Convert controller.Job to internal jobs.Job type
	job := &jobs.Job{ID: resp.Job.ID, Type: jobs.JobType(resp.Job.Type), Payload: resp.Job.Payload}
	result, jobErr := handler.Handle(jobCtx, job)
	status := controller.AckSucceeded
	var detail interface{} = result
	if jobErr != nil {
		status = controller.AckFailed
		detail = map[string]any{"error": jobErr.Error()}
	}

	if err := client.AckJob(jobCtx, agentID, resp.Job.ID, status, detail); err != nil {
		return fmt.Errorf("ack job: %w", err)
	}

	if jobErr != nil {
		return jobErr
	}
	return nil
}

type controllerLogPublisher struct {
	client *controller.Client
	agentID string
}

func (p *controllerLogPublisher) Publish(ctx context.Context, jobID string, reader io.Reader) error {
	return p.client.StreamLogs(ctx, p.agentID, jobID, reader)
}

func buildCapabilities(cfg config.Config) []string {
	caps := []string{"deploy", "logs", "restart", "stop", "remove", "compose", "dockerfile", "image"}
	if cfg.AllowUnsafeCommands || cfg.SecurityBypass {
		caps = append(caps, "exec", "env-query")
	}
	if cfg.RequireImageDigest && !cfg.SecurityBypass {
		caps = append(caps, "digest-enforced")
	}
	return caps
}

func shouldRunInteractiveSetup(cfg config.Config) bool {
	if !cfg.InteractiveSetup {
		return false
	}
	if cfg.SecurityBypass {
		return false
	}
	if os.Getenv("DEPLOYBOT_SKIP_SETUP") != "" {
		return false
	}
	stdinFD := int(os.Stdin.Fd())
	stdoutFD := int(os.Stdout.Fd())
	if !term.IsTerminal(stdinFD) || !term.IsTerminal(stdoutFD) {
		return false
	}
	return true
}
