package dockerutil

import "strings"

const (
	AgentLabelManagedKey   = "deploybot.managed"
	AgentLabelManagedValue = "true"
	AgentImageRepository   = "deploybot"
)

var defaultAgentLabels = map[string]string{
	AgentLabelManagedKey: AgentLabelManagedValue,
}

// WithAgentLabels ensures the default agent labels are present on the provided map.
func WithAgentLabels(labels map[string]string) map[string]string {
	if labels == nil {
		labels = make(map[string]string, len(defaultAgentLabels))
	}
	for k, v := range defaultAgentLabels {
		if _, exists := labels[k]; !exists {
			labels[k] = v
		}
	}
	return labels
}

// DefaultImageLabels returns a fresh copy of the default labels used for agent-built images.
func DefaultImageLabels() map[string]string {
	labels := make(map[string]string, len(defaultAgentLabels))
	for k, v := range defaultAgentLabels {
		labels[k] = v
	}
	return labels
}

// EnsureAgentImageTag guarantees that the provided tag is namespaced for agent-built images.
func EnsureAgentImageTag(tag string) string {
	if tag == "" {
		return tag
	}
	if strings.Contains(tag, "/") {
		return tag
	}
	return AgentImageRepository + "/" + tag
}
