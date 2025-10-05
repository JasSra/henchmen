"""
DeployBot Controller CLI
"""
import click
import httpx
import sys
from typing import Optional


DEFAULT_API_URL = "http://localhost:8080"


@click.group()
@click.option('--api-url', default=DEFAULT_API_URL, help='API base URL')
@click.pass_context
def cli(ctx, api_url):
    """DeployBot Controller CLI"""
    ctx.ensure_object(dict)
    ctx.obj['API_URL'] = api_url


@cli.command()
@click.option('--repo', required=True, help='Repository name (org/repo)')
@click.option('--ref', required=True, help='Git ref (branch, tag, or commit SHA)')
@click.option('--host', required=True, help='Target host for deployment')
@click.pass_context
def deploy(ctx, repo: str, ref: str, host: str):
    """Create a deployment job"""
    api_url = ctx.obj['API_URL']
    
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{api_url}/v1/jobs",
                json={
                    "repo": repo,
                    "ref": ref,
                    "host": host,
                    "metadata": {
                        "trigger": "cli"
                    }
                }
            )
            
            if response.status_code == 201:
                data = response.json()
                job = data.get('job', {})
                click.echo(f"✓ Job created successfully")
                click.echo(f"  Job ID: {job.get('id')}")
                click.echo(f"  Repo: {job.get('repo')}")
                click.echo(f"  Ref: {job.get('ref')}")
                click.echo(f"  Host: {job.get('host')}")
                click.echo(f"  Status: {job.get('status')}")
            else:
                click.echo(f"✗ Failed to create job: {response.status_code}", err=True)
                click.echo(response.text, err=True)
                sys.exit(1)
    
    except httpx.ConnectError:
        click.echo(f"✗ Failed to connect to API at {api_url}", err=True)
        click.echo("  Make sure the controller is running.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--host', help='Filter logs by host')
@click.option('--app', help='Filter logs by application')
@click.option('--follow', '-f', is_flag=True, help='Follow log stream')
@click.pass_context
def logs(ctx, host: Optional[str], app: Optional[str], follow: bool):
    """View deployment logs"""
    api_url = ctx.obj['API_URL']
    
    if follow:
        # Stream logs via SSE
        click.echo("Streaming logs... (Press Ctrl+C to stop)")
        try:
            params = {}
            if host:
                params['host'] = host
            if app:
                params['app'] = app
            
            with httpx.Client(timeout=None) as client:
                with client.stream('GET', f"{api_url}/v1/logs/stream", params=params) as response:
                    for line in response.iter_lines():
                        if line.startswith('data: '):
                            data = line[6:]  # Remove 'data: ' prefix
                            if data and data != '{}':
                                click.echo(data)
        
        except KeyboardInterrupt:
            click.echo("\nStopped streaming.")
        except httpx.ConnectError:
            click.echo(f"✗ Failed to connect to API at {api_url}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"✗ Error: {str(e)}", err=True)
            sys.exit(1)
    else:
        # Fetch recent logs (not implemented in API, using jobs as proxy)
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{api_url}/v1/jobs")
                
                if response.status_code == 200:
                    jobs = response.json()
                    
                    # Filter by host/app if provided
                    filtered_jobs = jobs
                    if host:
                        filtered_jobs = [j for j in filtered_jobs if j.get('host') == host]
                    if app:
                        filtered_jobs = [
                            j for j in filtered_jobs 
                            if j.get('metadata', {}).get('app') == app
                        ]
                    
                    if not filtered_jobs:
                        click.echo("No jobs found.")
                        return
                    
                    click.echo(f"Recent jobs (total: {len(filtered_jobs)}):\n")
                    for job in filtered_jobs[:20]:  # Show last 20
                        status_icon = {
                            'pending': '⏳',
                            'running': '▶️',
                            'success': '✓',
                            'failed': '✗',
                            'cancelled': '⊗'
                        }.get(job.get('status'), '?')
                        
                        click.echo(f"{status_icon} [{job.get('id')[:8]}] {job.get('repo')} @ {job.get('ref')[:8]}")
                        click.echo(f"   Host: {job.get('host')} | Status: {job.get('status')}")
                        if job.get('error'):
                            click.echo(f"   Error: {job.get('error')}")
                        click.echo()
                else:
                    click.echo(f"✗ Failed to fetch jobs: {response.status_code}", err=True)
                    sys.exit(1)
        
        except httpx.ConnectError:
            click.echo(f"✗ Failed to connect to API at {api_url}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"✗ Error: {str(e)}", err=True)
            sys.exit(1)


@cli.command()
@click.argument('job_id')
@click.pass_context
def status(ctx, job_id: str):
    """Get job status"""
    api_url = ctx.obj['API_URL']
    
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{api_url}/v1/jobs/{job_id}")
            
            if response.status_code == 200:
                data = response.json()
                job = data.get('job', {})
                
                status_icon = {
                    'pending': '⏳',
                    'running': '▶️',
                    'success': '✓',
                    'failed': '✗',
                    'cancelled': '⊗'
                }.get(job.get('status'), '?')
                
                click.echo(f"Job Status {status_icon}\n")
                click.echo(f"  ID: {job.get('id')}")
                click.echo(f"  Repo: {job.get('repo')}")
                click.echo(f"  Ref: {job.get('ref')}")
                click.echo(f"  Host: {job.get('host')}")
                click.echo(f"  Status: {job.get('status')}")
                click.echo(f"  Created: {job.get('created_at')}")
                
                if job.get('started_at'):
                    click.echo(f"  Started: {job.get('started_at')}")
                if job.get('completed_at'):
                    click.echo(f"  Completed: {job.get('completed_at')}")
                if job.get('assigned_agent'):
                    click.echo(f"  Agent: {job.get('assigned_agent')}")
                if job.get('error'):
                    click.echo(f"  Error: {job.get('error')}")
                
                metadata = job.get('metadata', {})
                if metadata:
                    click.echo(f"\n  Metadata:")
                    for key, value in metadata.items():
                        click.echo(f"    {key}: {value}")
            
            elif response.status_code == 404:
                click.echo(f"✗ Job not found: {job_id}", err=True)
                sys.exit(1)
            else:
                click.echo(f"✗ Failed to get job: {response.status_code}", err=True)
                sys.exit(1)
    
    except httpx.ConnectError:
        click.echo(f"✗ Failed to connect to API at {api_url}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli(obj={})
