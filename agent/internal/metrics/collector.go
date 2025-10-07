package metrics

import (
	"context"
	"runtime"

	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/disk"
	"github.com/shirou/gopsutil/v3/mem"
)

// Snapshot contains host resource utilisation.
type Snapshot struct {
	CPUPercent float64
	MemPercent float64
	DiskFreeGB float64
}

// Collect gathers a quick snapshot of system metrics.
func Collect(ctx context.Context) (Snapshot, error) {
	var snap Snapshot
	percents, err := cpu.PercentWithContext(ctx, 0, false)
	if err == nil && len(percents) > 0 {
		snap.CPUPercent = percents[0]
	}
	if vm, err := mem.VirtualMemoryWithContext(ctx); err == nil {
		snap.MemPercent = vm.UsedPercent
	}
	// Estimate disk space from the root partition
	path := "/"
	if runtime.GOOS == "windows" {
		path = "C:"
	}
	if du, err := disk.UsageWithContext(ctx, path); err == nil {
		snap.DiskFreeGB = float64(du.Free) / (1024 * 1024 * 1024)
	}
	return snap, nil
}
