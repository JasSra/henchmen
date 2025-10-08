using System;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using Docker.DotNet;
using Docker.DotNet.Models;
using LibGit2Sharp;

namespace DeploybotAgent;

class Program
{
    private static readonly HttpClient httpClient = new();
    private static DockerClient? dockerClient;
    private static string? controllerUrl;
    private static string? hostname;
    private static string? agentId;
    private static int heartbeatInterval = 5;
    private static string workDir = "/tmp/deploybot-agent";
    
    static async Task Main(string[] args)
    {
        Console.WriteLine("DeployBot .NET Agent Starting...");
        
        // Load configuration from environment variables
        controllerUrl = Environment.GetEnvironmentVariable("CONTROLLER_URL") ?? "http://localhost:8080";
        hostname = Environment.GetEnvironmentVariable("AGENT_HOSTNAME") ?? Environment.MachineName;
        workDir = Environment.GetEnvironmentVariable("AGENT_WORK_DIR") ?? "/tmp/deploybot-agent";
        
        if (int.TryParse(Environment.GetEnvironmentVariable("HEARTBEAT_INTERVAL"), out int interval))
        {
            heartbeatInterval = interval;
        }
        
        Console.WriteLine($"Controller URL: {controllerUrl}");
        Console.WriteLine($"Hostname: {hostname}");
        Console.WriteLine($"Work Directory: {workDir}");
        Console.WriteLine($"Heartbeat Interval: {heartbeatInterval} seconds");
        
        // Create work directory
        Directory.CreateDirectory(workDir);
        
        // Initialize Docker client
        dockerClient = new DockerClientConfiguration().CreateClient();
        
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
        
        var success = false;
        var errorMessage = "";
        
        try
        {
            // 1. Clone/pull the repository
            var repoPath = await CloneOrUpdateRepository(job.Repo, job.Ref);
            
            // 2. Build Docker image (if Dockerfile exists)
            var imageName = await BuildDockerImage(repoPath, job.Repo);
            
            // 3. Deploy container
            await DeployContainer(imageName, job.Repo);
            
            Console.WriteLine($"✓ Job {job.Id} completed successfully!");
            success = true;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"✗ Job {job.Id} failed: {ex.Message}");
            errorMessage = ex.Message;
        }
        
        // 4. Report completion status to controller
        await ReportJobCompletion(job.Id, success, errorMessage);
    }
    
    static async Task<string> CloneOrUpdateRepository(string repo, string gitRef)
    {
        Console.WriteLine($"Cloning/updating repository {repo}...");
        
        var repoName = repo.Split('/').Last();
        var repoPath = Path.Combine(workDir, repoName);
        var repoUrl = $"https://github.com/{repo}.git";
        
        try
        {
            if (Directory.Exists(Path.Combine(repoPath, ".git")))
            {
                // Update existing repository
                Console.WriteLine($"  Repository exists, fetching updates...");
                using var repository = new Repository(repoPath);
                
                var remote = repository.Network.Remotes["origin"];
                var refSpecs = remote.FetchRefSpecs.Select(x => x.Specification);
                Commands.Fetch(repository, remote.Name, refSpecs, null, "");
                
                // Checkout the ref
                Commands.Checkout(repository, gitRef);
                Console.WriteLine($"  ✓ Updated and checked out {gitRef}");
            }
            else
            {
                // Clone new repository
                Console.WriteLine($"  Cloning from {repoUrl}...");
                Repository.Clone(repoUrl, repoPath);
                
                using var repository = new Repository(repoPath);
                Commands.Checkout(repository, gitRef);
                Console.WriteLine($"  ✓ Cloned and checked out {gitRef}");
            }
            
            return repoPath;
        }
        catch (Exception ex)
        {
            throw new Exception($"Failed to clone/update repository: {ex.Message}", ex);
        }
    }
    
    static async Task<string> BuildDockerImage(string repoPath, string repo)
    {
        var dockerfilePath = Path.Combine(repoPath, "Dockerfile");
        var imageName = $"{repo.Replace('/', '-').ToLower()}:latest";
        
        if (!File.Exists(dockerfilePath))
        {
            Console.WriteLine($"  No Dockerfile found, skipping build");
            return imageName;
        }
        
        Console.WriteLine($"Building Docker image {imageName}...");
        
        try
        {
            if (dockerClient == null)
            {
                throw new Exception("Docker client not initialized");
            }
            
            var buildParameters = new ImageBuildParameters
            {
                Tags = new List<string> { imageName },
                Dockerfile = "Dockerfile"
            };
            
            using var tarStream = CreateTarArchive(repoPath);
            await dockerClient.Images.BuildImageFromDockerfileAsync(
                buildParameters, 
                tarStream, 
                null,
                null,
                new Progress<JSONMessage>(),
                CancellationToken.None);
            
            Console.WriteLine($"  ✓ Built image {imageName}");
            return imageName;
        }
        catch (Exception ex)
        {
            throw new Exception($"Failed to build Docker image: {ex.Message}", ex);
        }
    }
    
    static Stream CreateTarArchive(string sourceDirectory)
    {
        var tarStream = new MemoryStream();
        using (var tar = new ICSharpCode.SharpZipLib.Tar.TarOutputStream(tarStream, System.Text.Encoding.UTF8))
        {
            tar.IsStreamOwner = false;
            AddDirectoryToTar(tar, sourceDirectory, "");
        }
        tarStream.Position = 0;
        return tarStream;
    }
    
    static void AddDirectoryToTar(ICSharpCode.SharpZipLib.Tar.TarOutputStream tar, string sourceDirectory, string basePath)
    {
        foreach (var file in Directory.GetFiles(sourceDirectory))
        {
            var entry = ICSharpCode.SharpZipLib.Tar.TarEntry.CreateTarEntry(Path.Combine(basePath, Path.GetFileName(file)));
            entry.Size = new FileInfo(file).Length;
            tar.PutNextEntry(entry);
            
            using (var fs = File.OpenRead(file))
            {
                fs.CopyTo(tar);
            }
            tar.CloseEntry();
        }
        
        foreach (var directory in Directory.GetDirectories(sourceDirectory))
        {
            AddDirectoryToTar(tar, directory, Path.Combine(basePath, Path.GetFileName(directory)));
        }
    }
    
    static async Task DeployContainer(string imageName, string repo)
    {
        var containerName = repo.Split('/').Last().ToLower();
        
        Console.WriteLine($"Deploying container {containerName}...");
        
        try
        {
            if (dockerClient == null)
            {
                throw new Exception("Docker client not initialized");
            }
            
            // Stop and remove existing container if it exists
            var containers = await dockerClient.Containers.ListContainersAsync(new ContainersListParameters { All = true });
            var existingContainer = containers.FirstOrDefault(c => c.Names.Any(n => n.Contains(containerName)));
            
            if (existingContainer != null)
            {
                Console.WriteLine($"  Stopping existing container...");
                await dockerClient.Containers.StopContainerAsync(existingContainer.ID, new ContainerStopParameters());
                await dockerClient.Containers.RemoveContainerAsync(existingContainer.ID, new ContainerRemoveParameters());
            }
            
            // Create and start new container
            var createParams = new CreateContainerParameters
            {
                Image = imageName,
                Name = containerName,
                HostConfig = new HostConfig
                {
                    RestartPolicy = new RestartPolicy { Name = RestartPolicyKind.UnlessStopped },
                    PublishAllPorts = true
                }
            };
            
            var container = await dockerClient.Containers.CreateContainerAsync(createParams);
            await dockerClient.Containers.StartContainerAsync(container.ID, new ContainerStartParameters());
            
            Console.WriteLine($"  ✓ Container {containerName} deployed successfully");
        }
        catch (Exception ex)
        {
            throw new Exception($"Failed to deploy container: {ex.Message}", ex);
        }
    }
    
    static async Task ReportJobCompletion(string jobId, bool success, string? error = null)
    {
        try
        {
            var status = success ? "success" : "failed";
            var payload = new
            {
                status = status,
                error = error
            };
            
            var response = await httpClient.PutAsJsonAsync(
                $"{controllerUrl}/v1/jobs/{jobId}/status",
                payload
            );
            
            if (response.IsSuccessStatusCode)
            {
                Console.WriteLine($"  ✓ Reported job completion to controller");
            }
            else
            {
                Console.WriteLine($"  ⚠ Failed to report job completion: {response.StatusCode}");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"  ⚠ Error reporting job completion: {ex.Message}");
        }
    }
}

// DTOs for API communication
record AgentResponse(string Id, string Hostname);
record HeartbeatResponse(JobResponse? Job);
record JobResponse(string Id, string Repo, string Ref, string Host, string Status);
