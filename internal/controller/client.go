package controller

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path"
	"strings"
	"time"

	"deploybot-agent/internal/jobs"
)

// Client handles communication with the DeployBot controller.
type Client struct {
	baseURL    *url.URL
	httpClient *http.Client
	agentToken string
}

type TLSConfig struct {
	AllowInsecure bool
	CAFile        string
	CAPins        []string
	ClientCert    string
	ClientKey     string
}

type clientOptions struct {
	tls            TLSConfig
	securityBypass bool
}

// Option customises controller client behaviour.
type Option func(*clientOptions)

// WithTLSConfig applies TLS hardening / override parameters.
func WithTLSConfig(cfg TLSConfig) Option {
	return func(o *clientOptions) {
		o.tls = cfg
	}
}

// WithSecurityBypass relaxes strict enforcement in trusted environments.
func WithSecurityBypass() Option {
	return func(o *clientOptions) {
		o.securityBypass = true
	}
}

// New creates a new controller client.
func New(base, token string, opts ...Option) (*Client, error) {
	cfg := clientOptions{tls: TLSConfig{}}
	for _, opt := range opts {
		opt(&cfg)
	}

	u, err := url.Parse(base)
	if err != nil {
		return nil, err
	}

	if u.Scheme != "https" && !cfg.tls.AllowInsecure && !cfg.securityBypass {
		return nil, errors.New("controller URL must be https; override with allow-insecure-controller")
	}

	tlsConfig, err := buildTLSConfig(u.Hostname(), cfg)
	if err != nil {
		return nil, err
	}

	transport := &http.Transport{TLSClientConfig: tlsConfig}
	transport.Proxy = http.ProxyFromEnvironment
	transport.ForceAttemptHTTP2 = true

	return &Client{
		baseURL:    u,
		httpClient: &http.Client{Timeout: 30 * time.Second, Transport: transport},
		agentToken: token,
	}, nil
}

func buildTLSConfig(serverName string, opts clientOptions) (*tls.Config, error) {
	tlsCfg := &tls.Config{MinVersion: tls.VersionTLS12}
	if serverName != "" {
		tlsCfg.ServerName = serverName
	}
	if opts.tls.AllowInsecure || opts.securityBypass {
		tlsCfg.InsecureSkipVerify = true
	}
	if opts.tls.CAFile != "" {
		data, err := os.ReadFile(opts.tls.CAFile)
		if err != nil {
			return nil, fmt.Errorf("failed to read controller CA: %w", err)
		}
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM(data) {
			return nil, errors.New("controller CA file is invalid")
		}
		tlsCfg.RootCAs = pool
	}
	if opts.tls.ClientCert != "" || opts.tls.ClientKey != "" {
		if opts.tls.ClientCert == "" || opts.tls.ClientKey == "" {
			return nil, errors.New("client cert and key must both be provided")
		}
		cert, err := tls.LoadX509KeyPair(opts.tls.ClientCert, opts.tls.ClientKey)
		if err != nil {
			return nil, fmt.Errorf("failed to load client certificate: %w", err)
		}
		tlsCfg.Certificates = []tls.Certificate{cert}
	}
	pins, err := normalizePins(opts.tls.CAPins)
	if err != nil {
		return nil, err
	}
	if len(pins) > 0 {
		tlsCfg.VerifyPeerCertificate = func(rawCerts [][]byte, _ [][]*x509.Certificate) error {
			for _, der := range rawCerts {
				hash := sha256.Sum256(der)
				for _, pin := range pins {
					if bytes.Equal(hash[:], pin) {
						return nil
					}
				}
			}
			return errors.New("controller certificate did not match any configured pins")
		}
	}
	return tlsCfg, nil
}

func normalizePins(values []string) ([][]byte, error) {
	if len(values) == 0 {
		return nil, nil
	}
	result := make([][]byte, 0, len(values))
	for _, v := range values {
		trim := strings.TrimSpace(strings.ToLower(v))
		if trim == "" {
			continue
		}
		trim = strings.TrimPrefix(trim, "sha256:")
		trim = strings.ReplaceAll(trim, ":", "")
		decoded, err := hex.DecodeString(trim)
		if err != nil {
			return nil, fmt.Errorf("invalid certificate pin %q: %w", v, err)
		}
		result = append(result, decoded)
	}
	return result, nil
}

// RegisterRequest contains the payload for registering the agent.
type RegisterRequest struct {
	Token         string   `json:"token"`
	Metrics       Metrics  `json:"metrics"`
	DockerVersion string   `json:"docker_version"`
	Hostname      string   `json:"hostname"`
	Capabilities  []string `json:"capabilities,omitempty"`
}

// Metrics summarises host resource utilisation.
type Metrics struct {
	CPUPercent float64 `json:"cpu_percent"`
	MemPercent float64 `json:"mem_percent"`
	DiskFreeGB float64 `json:"disk_free_gb"`
}

// RegisterResponse returns the permanent agent credentials.
type RegisterResponse struct {
	AgentID    string `json:"agent_id"`
	AgentToken string `json:"agent_token"`
}

// HeartbeatRequest is sent periodically with metrics and inventory.
type HeartbeatRequest struct {
	Metrics      Metrics             `json:"metrics"`
	Inventory    []InventoryResource `json:"inventory"`
	Capabilities []string            `json:"capabilities,omitempty"`
}

// InventoryResource describes a running container.
type InventoryResource struct {
	Name   string            `json:"name"`
	Image  string            `json:"image"`
	Ports  map[string]string `json:"ports"`
	Status string            `json:"status"`
	Health string            `json:"health"`
}

// HeartbeatResponse conveys optional pending work.
type HeartbeatResponse struct {
	Job *jobs.Job `json:"job"`
}

// AckStatus is the result of running a job.
type AckStatus string

const (
	AckSucceeded AckStatus = "succeeded"
	AckFailed    AckStatus = "failed"
)

// JobAckRequest acknowledges job completion.
type JobAckRequest struct {
	Status AckStatus   `json:"status"`
	Detail interface{} `json:"detail,omitempty"`
}

// Register registers the agent with the controller.
func (c *Client) Register(ctx context.Context, req RegisterRequest) (RegisterResponse, error) {
	var resp RegisterResponse
	if err := c.do(ctx, http.MethodPost, "/v1/agents/register", req, &resp); err != nil {
		return RegisterResponse{}, err
	}
	c.agentToken = resp.AgentToken
	return resp, nil
}

// Heartbeat sends periodic state updates.
func (c *Client) Heartbeat(ctx context.Context, agentID string, req HeartbeatRequest) (HeartbeatResponse, error) {
	var resp HeartbeatResponse
	endpoint := fmt.Sprintf("/v1/agents/%s/heartbeat", agentID)
	if err := c.do(ctx, http.MethodPost, endpoint, req, &resp); err != nil {
		return HeartbeatResponse{}, err
	}
	return resp, nil
}

// AckJob notifies the controller that a job completed.
func (c *Client) AckJob(ctx context.Context, agentID, jobID string, status AckStatus, detail interface{}) error {
	endpoint := fmt.Sprintf("/v1/agents/%s/jobs/%s", agentID, jobID)
	return c.do(ctx, http.MethodPost, endpoint, JobAckRequest{Status: status, Detail: detail}, nil)
}

// StreamLogs streams container logs to the controller via chunked POST.
func (c *Client) StreamLogs(ctx context.Context, agentID, jobID string, reader io.Reader) error {
	endpoint := fmt.Sprintf("/v1/agents/%s/jobs/%s/logs", agentID, jobID)
	rel := *c.baseURL
	rel.Path = path.Join(c.baseURL.Path, endpoint)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, rel.String(), reader)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "text/plain")
	if c.agentToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.agentToken)
	}
	res, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode >= 300 {
		body, _ := io.ReadAll(res.Body)
		return fmt.Errorf("stream logs failed: %s", string(body))
	}
	return nil
}

func (c *Client) do(ctx context.Context, method, endpoint string, payload interface{}, out interface{}) error {
	rel := *c.baseURL
	rel.Path = path.Join(c.baseURL.Path, endpoint)

	var body io.Reader
	if payload != nil {
		data, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, rel.String(), body)
	if err != nil {
		return err
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.agentToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.agentToken)
	}

	res, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode >= 300 {
		data, _ := io.ReadAll(res.Body)
		return fmt.Errorf("controller request failed (%d): %s", res.StatusCode, string(data))
	}
	if out == nil {
		return nil
	}
	return json.NewDecoder(res.Body).Decode(out)
}
