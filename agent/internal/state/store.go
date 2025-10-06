package state

import (
    "encoding/json"
    "errors"
    "fmt"
    "net"
    "os"
    "path/filepath"
    "sync"
    "time"
)

// AgentState holds persistent agent metadata and runtime allocations.
type AgentState struct {
    AgentID             string                      `json:"agent_id"`
    AgentToken          string                      `json:"agent_token,omitempty"`
    AgentTokenEncrypted string                      `json:"agent_token_encrypted,omitempty"`
    TokenUpdatedAt      time.Time                   `json:"token_updated_at,omitempty"`
    Ports               map[string]int              `json:"ports"`
    Deployments         map[string]DeploymentRecord `json:"deployments"`
}

// DeploymentRecord tracks the last known deployment for rollback purposes.
type DeploymentRecord struct { Name string `json:"name"`; ContainerID string `json:"container_id"`; Compose bool `json:"compose"` }

// Store wraps AgentState with persistence helpers.
type Store struct {
    path          string
    state         AgentState
    mu            sync.RWMutex
    cipher        Cipher
    encryptTokens bool
}

type storeOptions struct { cipher Cipher; encryptTokens bool }

// Option configures Store behaviour at creation time.
type Option func(*storeOptions)

// WithCipher registers a cipher that can decrypt existing state.
func WithCipher(c Cipher) Option { return func(o *storeOptions) { o.cipher = c } }

// WithTokenEncryption toggles encryption when persisting sensitive fields.
func WithTokenEncryption(enabled bool) Option { return func(o *storeOptions) { o.encryptTokens = enabled } }

// Open loads state from path, creating an empty state if the file is absent.
func Open(path string, opts ...Option) (*Store, error) {
    if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil { return nil, err }
    config := storeOptions{}
    for _, opt := range opts { opt(&config) }
    s := &Store{path: path, cipher: config.cipher, encryptTokens: config.encryptTokens && config.cipher != nil}

    data, err := os.ReadFile(path)
    if errors.Is(err, os.ErrNotExist) {
        s.state = AgentState{Ports: map[string]int{}, Deployments: map[string]DeploymentRecord{}}
        return s, nil
    }
    if err != nil { return nil, err }
    if err := json.Unmarshal(data, &s.state); err != nil { return nil, err }
    if s.state.Ports == nil { s.state.Ports = map[string]int{} }
    if s.state.Deployments == nil { s.state.Deployments = map[string]DeploymentRecord{} }
    if s.encryptTokens && s.cipher != nil {
        if s.state.AgentToken != "" { if err := s.migratePlaintextToken(); err != nil { return nil, err } } else if s.state.AgentTokenEncrypted != "" { if err := s.rotateEncryptedToken(); err != nil { return nil, err } }
    }
    return s, nil
}

// Save persists current state atomically.
func (s *Store) Save() error {
    s.mu.RLock(); defer s.mu.RUnlock()
    tmpPath := s.path + ".tmp"
    data, err := json.MarshalIndent(&s.state, "", "  ")
    if err != nil { return err }
    if err := os.WriteFile(tmpPath, data, 0o600); err != nil { return err }
    return os.Rename(tmpPath, s.path)
}

// SetAgent records the agentID/token pair and persists immediately.
func (s *Store) SetAgent(id, token string) error {
    s.mu.Lock(); defer s.mu.Unlock()
    s.state.AgentID = id
    if s.encryptTokens && s.cipher != nil { if err := s.encryptTokenLocked(token); err != nil { return err } } else { s.state.AgentToken = token; s.state.AgentTokenEncrypted = ""; s.state.TokenUpdatedAt = time.Now().UTC() }
    return s.saveLocked()
}

// AgentCredentials returns the stored ID/token if present.
func (s *Store) AgentCredentials() (string, string, error) {
    s.mu.RLock(); defer s.mu.RUnlock()
    token := s.state.AgentToken
    if token == "" && s.state.AgentTokenEncrypted != "" {
        if s.cipher == nil { return "", "", errors.New("state contains encrypted agent token but cipher is not configured") }
        plaintext, err := s.cipher.Decrypt(s.state.AgentTokenEncrypted)
        if err != nil { return "", "", err }
        token = string(plaintext)
    }
    return s.state.AgentID, token, nil
}

// ReservePort reserves a TCP port with the given key. If preferred > 0 we try to use it, otherwise scan.
func (s *Store) ReservePort(key string, preferred int) (int, error) {
    s.mu.Lock(); defer s.mu.Unlock()
    if port, ok := s.state.Ports[key]; ok { return port, nil }
    var port int; var err error
    if preferred > 0 { if err = ensureAvailable(preferred); err == nil { port = preferred } }
    if port == 0 { port, err = scanPortRange(20000, 65000); if err != nil { return 0, err } }
    s.state.Ports[key] = port
    if err := s.saveLocked(); err != nil { return 0, err }
    return port, nil
}

// ReleasePort frees a previously reserved port.
func (s *Store) ReleasePort(key string) error { s.mu.Lock(); defer s.mu.Unlock(); delete(s.state.Ports, key); return s.saveLocked() }

// RecordDeployment stores deployment metadata.
func (s *Store) RecordDeployment(name string, record DeploymentRecord) error { s.mu.Lock(); defer s.mu.Unlock(); s.state.Deployments[name] = record; return s.saveLocked() }

// LastDeployment fetches the last deployment for a given name.
func (s *Store) LastDeployment(name string) (DeploymentRecord, bool) { s.mu.RLock(); defer s.mu.RUnlock(); rec, ok := s.state.Deployments[name]; return rec, ok }

func (s *Store) saveLocked() error {
    tmpPath := s.path + ".tmp"
    data, err := json.MarshalIndent(&s.state, "", "  ")
    if err != nil { return err }
    if err := os.WriteFile(tmpPath, data, 0o600); err != nil { return err }
    return os.Rename(tmpPath, s.path)
}

func ensureAvailable(port int) error {
    ln, err := net.Listen("tcp", fmt.Sprintf(":"+"%d", port))
    if err != nil { return err }
    return ln.Close()
}

func (s *Store) encryptTokenLocked(token string) error {
    if s.cipher == nil { return errors.New("encryption cipher not configured") }
    enc, err := s.cipher.Encrypt([]byte(token))
    if err != nil { return err }
    s.state.AgentToken = ""
    s.state.AgentTokenEncrypted = enc
    s.state.TokenUpdatedAt = time.Now().UTC()
    return nil
}

func (s *Store) migratePlaintextToken() error {
    s.mu.Lock(); defer s.mu.Unlock()
    token := s.state.AgentToken
    if token == "" { return nil }
    if err := s.encryptTokenLocked(token); err != nil { return err }
    return s.saveLocked()
}

func (s *Store) rotateEncryptedToken() error {
    s.mu.Lock(); defer s.mu.Unlock()
    if s.state.AgentTokenEncrypted == "" { return nil }
    plaintext, err := s.cipher.Decrypt(s.state.AgentTokenEncrypted)
    if err != nil { return err }
    if err := s.encryptTokenLocked(string(plaintext)); err != nil { return err }
    return s.saveLocked()
}

func scanPortRange(start, end int) (int, error) {
    for p := start; p <= end; p++ { if err := ensureAvailable(p); err == nil { return p, nil } }
    return 0, errors.New("no free ports found in range")
}
