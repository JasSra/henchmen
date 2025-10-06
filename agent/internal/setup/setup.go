package setup

import (
    "fmt"
    "os"
    "time"

    "deploybot-agent/internal/config"
)

// Run performs basic interactive checks and prints guidance.
func Run(cfg config.Config) error {
    // Minimal placeholder: verify data/work dir writable
    for _, p := range []string{cfg.DataDir, cfg.WorkDir} {
        if p == "" { continue }
        if err := os.MkdirAll(p, 0o755); err != nil { return fmt.Errorf("cannot create %s: %w", p, err) }
        test := p + string(os.PathSeparator) + fmt.Sprintf(".writetest-%d", time.Now().UnixNano())
        if err := os.WriteFile(test, []byte("ok"), 0o600); err != nil { return fmt.Errorf("write test failed for %s: %w", p, err) }
        _ = os.Remove(test)
    }
    return nil
}
