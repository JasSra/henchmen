using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Docker.DotNet;
using Docker.DotNet.Models;

namespace DeploybotAgent;

class Program
{
    private static readonly HttpClient httpClient = new();
    private static string? controllerUrl;
    private static string? hostname;
    private static string? agentId;
    private static int heartbeatInterval = 5;
    
    static async Task Main(string[] args)
    {
        Console.WriteLine("DeployBot .NET Agent Starting...");
        
        // Load configuration from environment variables
        controllerUrl = Environment.GetEnvironmentVariable("CONTROLLER_URL") ?? "http://localhost:8080";
        hostname = Environment.GetEnvironmentVariable("AGENT_HOSTNAME") ?? Environment.MachineName;
        
        if (int.TryParse(Environment.GetEnvironmentVariable("HEARTBEAT_INTERVAL"), out int interval))
        {
            heartbeatInterval = interval;
        }
        
        Console.WriteLine($"Controller URL: {controllerUrl}");
        Console.WriteLine($"Hostname: {hostname}");
        Console.WriteLine($"Heartbeat Interval: {heartbeatInterval} seconds");
        
        // Register with controller
        if (!await RegisterAgent())
        {
            Console.WriteLine("Failed to register with controller. Exiting.");
            return;
        }
        
        // Start heartbeat loop
        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (sender, e) =>
        {
            e.Cancel = true;
            cts.Cancel();
            Console.WriteLine("\nShutting down...");
        };
        
        await RunHeartbeatLoop(cts.Token);
    }
    
    static async Task<bool> RegisterAgent()
    {
        try
        {
            Console.WriteLine("Registering agent with controller...");
            
            var registration = new
            {
                hostname = hostname,
                capabilities = new
                {
                    platform = Environment.OSVersion.Platform.ToString(),
                    dotnet_version = Environment.Version.ToString(),
                    agent_type = "dotnet"
                }
            };
            
            var response = await httpClient.PostAsJsonAsync(
                $"{controllerUrl}/v1/agents/register",
                registration
            );
            
            if (response.IsSuccessStatusCode)
            {
                var result = await response.Content.ReadFromJsonAsync<AgentResponse>();
                agentId = result?.Id;
                Console.WriteLine($"✓ Registered successfully. Agent ID: {agentId}");
                return true;
            }
            else
            {
                Console.WriteLine($"✗ Registration failed: {response.StatusCode}");
                var error = await response.Content.ReadAsStringAsync();
                Console.WriteLine($"  Error: {error}");
                return false;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"✗ Registration error: {ex.Message}");
            return false;
        }
    }
    
    static async Task RunHeartbeatLoop(CancellationToken cancellationToken)
    {
        Console.WriteLine("Starting heartbeat loop...");
        
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                var job = await SendHeartbeat();
                
                if (job != null)
                {
                    Console.WriteLine($"Received job: {job.Id}");
                    await ExecuteJob(job);
                }
                
                await Task.Delay(TimeSpan.FromSeconds(heartbeatInterval), cancellationToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Heartbeat error: {ex.Message}");
                await Task.Delay(TimeSpan.FromSeconds(heartbeatInterval), cancellationToken);
            }
        }
    }
    
    static async Task<JobResponse?> SendHeartbeat()
    {
        try
        {
            var heartbeat = new { status = "online" };
            
            var response = await httpClient.PostAsJsonAsync(
                $"{controllerUrl}/v1/agents/{agentId}/heartbeat",
                heartbeat
            );
            
            if (response.IsSuccessStatusCode)
            {
                var result = await response.Content.ReadFromJsonAsync<HeartbeatResponse>();
                return result?.Job;
            }
            
            return null;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Heartbeat error: {ex.Message}");
            return null;
        }
    }
    
    static async Task ExecuteJob(JobResponse job)
    {
        Console.WriteLine($"Executing job {job.Id}");
        Console.WriteLine($"  Repo: {job.Repo}");
        Console.WriteLine($"  Ref: {job.Ref}");
        Console.WriteLine($"  Host: {job.Host}");
        
        // In a real implementation, this would:
        // 1. Clone/pull the repository
        // 2. Checkout the specified ref
        // 3. Build Docker images if needed
        // 4. Deploy containers
        // 5. Report progress/logs to controller
        // 6. Update job status (success/failure)
        
        // Simulate deployment
        Console.WriteLine("Simulating deployment...");
        await Task.Delay(2000);
        Console.WriteLine($"✓ Job {job.Id} completed successfully!");
    }
}

// DTOs for API communication
record AgentResponse(string Id, string Hostname);
record HeartbeatResponse(JobResponse? Job);
record JobResponse(string Id, string Repo, string Ref, string Host, string Status);
