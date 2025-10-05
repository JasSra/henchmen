package jobs

import "encoding/json"

// JobType enumerates supported job kinds.
type JobType string

const (
	JobDeploy   JobType = "deploy"
	JobRestart  JobType = "restart"
	JobStop     JobType = "stop"
	JobRemove   JobType = "remove"
	JobLogs     JobType = "logs"
	JobExec     JobType = "exec"
	JobQueryEnv JobType = "query_env"
)

// Job describes a unit of work assigned by the controller.
type Job struct {
	ID      string          `json:"id"`
	Type    JobType         `json:"type"`
	Payload json.RawMessage `json:"payload"`
}

// DeployJobPayload is the structure for deploy jobs.
type DeployJobPayload struct {
	Name            string            `json:"name"`
	RepositoryURL   string            `json:"repository_url"`
	Ref             string            `json:"ref"`
	Strategy        string            `json:"strategy"`
	Environment     map[string]string `json:"environment"`
	Volumes         []VolumeMapping   `json:"volumes"`
	Ports           []PortMapping     `json:"ports"`
	ComposeFile     string            `json:"compose_file"`
	ComposeProject  string            `json:"compose_project"`
	Dockerfile      string            `json:"dockerfile"`
	Image           string            `json:"image"`
	ImageDigest     string            `json:"image_digest"`
	ImageSignatures []string          `json:"image_signatures"`
	HealthCheck     HealthCheckSpec   `json:"health_check"`
	RestartPolicy   string            `json:"restart_policy"`
	LogsTailLines   int               `json:"logs_tail_lines"`
	LogsFollowMins  int               `json:"logs_follow_minutes"`
	CommitSHA       string            `json:"commit_sha"`
}

// HealthCheckSpec defines how to verify a service is healthy.
type HealthCheckSpec struct {
	Type            string `json:"type"`
	Endpoint        string `json:"endpoint"`
	ExpectedStatus  int    `json:"expected_status"`
}

// VolumeMapping maps a host path to a container path.
type VolumeMapping struct {
	Source string `json:"source"`
	Target string `json:"target"`
}

// PortMapping allows explicit or automatic port assignments.
type PortMapping struct {
	Key      string `json:"key"`
	Target   int    `json:"target"`
	Published string `json:"published"`
	Protocol string `json:"protocol"`
}

// ContainerJobPayload describes container selection actions.
type ContainerJobPayload struct {
	Name      string `json:"name"`
	Container string `json:"container"`
}

// LogsJobPayload carries log streaming parameters.
type LogsJobPayload struct {
	Name        string `json:"name"`
	Container   string `json:"container"`
	Tail        int    `json:"tail"`
	FollowMins  int    `json:"follow_minutes"`
}

// ExecJobPayload describes command execution requests on the host.
type ExecJobPayload struct {
	Command        []string          `json:"command"`
	Environment    map[string]string `json:"environment"`
	TimeoutSeconds int               `json:"timeout_seconds"`
	WorkingDir     string            `json:"working_dir"`
}

// EnvQueryPayload requests specific environment variables from the agent host.
type EnvQueryPayload struct {
	Keys []string `json:"keys"`
}
