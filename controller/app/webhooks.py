"""
GitHub webhook handler with HMAC verification (moved under controller/app)
"""
import hmac
import hashlib
import yaml
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException
from app.models import GitHubPushEvent, JobCreate


class WebhookHandler:
    """Handle GitHub webhooks and create deployment jobs"""
    
    def __init__(self, secret: str, config_path: str = "./controller/config/apps.yaml"):
        self.secret = secret
        self.config_path = config_path
        self.apps_config: Dict = {}
        self.load_config()
    
    def load_config(self):
        """Load apps configuration from YAML file"""
        config_file = Path(self.config_path)
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f)
                self.apps_config = data.get('apps', [])
        else:
            self.apps_config = []
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify GitHub webhook HMAC signature.
        
        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value
        
        Returns:
            True if signature is valid
        """
        if not signature:
            return False
        
        # GitHub sends: sha256=<hex_digest>
        if not signature.startswith('sha256='):
            return False
        
        expected_signature = signature[7:]  # Remove 'sha256=' prefix
        
        # Compute HMAC
        mac = hmac.new(
            self.secret.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha256
        )
        computed_signature = mac.hexdigest()
        
        # Constant-time comparison
        return hmac.compare_digest(computed_signature, expected_signature)
    
    def get_branch_from_ref(self, ref: str) -> str:
        """Extract branch name from ref (refs/heads/main -> main)"""
        if ref.startswith('refs/heads/'):
            return ref[11:]
        return ref
    
    def find_hosts_for_repo(
        self,
        repo: str,
        branch: str
    ) -> List[tuple[str, str]]:
        """
        Find hosts that should receive deployment for this repo and branch.
        
        Returns:
            List of (app_name, hostname) tuples
        """
        hosts = []
        
        for app in self.apps_config:
            # Check if repo matches
            if app.get('repo') != repo:
                continue
            
            # Check if deploy_on_push is enabled
            if not app.get('deploy_on_push', False):
                continue
            
            # Check if branch is in allowed branches
            allowed_branches = app.get('branches', [])
            if allowed_branches and branch not in allowed_branches:
                continue
            
            # Add all hosts for this app
            app_name = app.get('name', repo.split('/')[-1])
            for host in app.get('hosts', []):
                hosts.append((app_name, host))
        
        return hosts
    
    def process_push_event(self, event: GitHubPushEvent) -> List[JobCreate]:
        """
        Process GitHub push event and create job requests.
        
        Args:
            event: GitHub push event payload
        
        Returns:
            List of JobCreate objects
        """
        jobs = []
        
        # Extract repo and branch
        repo = event.repository.full_name
        branch = self.get_branch_from_ref(event.ref)
        commit_sha = event.after
        
        # Find matching hosts
        hosts = self.find_hosts_for_repo(repo, branch)
        
        # Create job for each host
        for app_name, hostname in hosts:
            job = JobCreate(
                repo=repo,
                ref=commit_sha,  # Use commit SHA for exact deployment
                host=hostname,
                metadata={
                    'app': app_name,
                    'branch': branch,
                    'commit_message': event.head_commit.message if event.head_commit else '',
                    'trigger': 'github_webhook'
                }
            )
            jobs.append(job)
        
        return jobs
