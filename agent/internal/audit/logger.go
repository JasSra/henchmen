package audit

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Logger persists structured audit events as JSON lines using a persistent file handle.
type Logger struct {
	mu   sync.Mutex
	file *os.File
}

// NewLogger initialises an audit logger writing to the given path.
func NewLogger(path string) (*Logger, error) {
	if path == "" {
		return &Logger{}, nil
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o640)
	if err != nil {
		return nil, err
	}
	return &Logger{file: f}, nil
}

// Close releases the underlying file handle.
func (l *Logger) Close() error {
	if l == nil || l.file == nil {
		return nil
	}
	return l.file.Close()
}

// Log writes an audit entry with the supplied event name and metadata.
func (l *Logger) Log(event string, fields map[string]interface{}) error {
	if l == nil || l.file == nil {
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
	l.mu.Lock()
	defer l.mu.Unlock()
	_, err = l.file.Write(append(data, '\n'))
	return err
}
