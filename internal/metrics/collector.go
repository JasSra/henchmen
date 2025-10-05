package metrics

import (
	"context"
	"runtime"
	"time"

	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/disk"
	"github.com/shirou/gopsutil/v3/mem"
)

// Snapshot captures point-in-time host metrics.
type Snapshot struct {
	CPUPercent float64
	MemPercent float64
	DiskFreeGB float64
}

// Collect gathers CPU, memory and root filesystem free space metrics.
func Collect(ctx context.Context) (Snapshot, error) {
	var snap Snapshot

	// CPU percent sampling - using short interval to avoid blocking forever on shutdown.
	interval := 300 * time.Millisecond
	if runtime.GOOS == "linux" {
		interval = 150 * time.Millisecond
	}

	cpuCtx, cancel := context.WithTimeout(ctx, interval+200*time.Millisecond)
	defer cancel()
	percents, err := cpu.PercentWithContext(cpuCtx, interval, false)
	if err == nil && len(percents) > 0 {
		snap.CPUPercent = percents[0]
	}

	if vm, err := mem.VirtualMemoryWithContext(ctx); err == nil {
		snap.MemPercent = vm.UsedPercent
	}

	if du, err := disk.UsageWithContext(ctx, "/"); err == nil {
		snap.DiskFreeGB = float64(du.Free) / (1024 * 1024 * 1024)
	}

	return snap, nil
}

