package audit

import (
    "encoding/json"
    "os"
    "path/filepath"
    "sync"
    "time"
)

// Logger persists structured audit events as JSON lines.
type Logger struct {
    path string
    mu   sync.Mutex
}

// NewLogger initialises an audit logger writing to the given path.
func NewLogger(path string) (*Logger, error) {
    if path == "" {
        return &Logger{}, nil
    }
    if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
        return nil, err
    }
    return &Logger{path: path}, nil
}

// Log writes an audit entry with the supplied event name and metadata.
func (l *Logger) Log(event string, fields map[string]interface{}) error {
    if l == nil {
        return nil
    }
    l.mu.Lock()
    defer l.mu.Unlock()

    if l.path == "" {
        return nil
    }

    entry := map[string]interface{}{
        "timestamp": time.Now().UTC().Format(time.RFC3339Nano),
        "event":     event,
    }
    for k, v := range fields {
        entry[k] = v
    }

    data, err := json.Marshal(entry)
    if err != nil {
        return err
    }

    f, err := os.OpenFile(l.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o640)
    if err != nil {
        return err
    }
    defer f.Close()

    if _, err := f.Write(append(data, '\n')); err != nil {
        return err
    }
    return nil
}
