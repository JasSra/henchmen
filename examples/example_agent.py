#!/usr/bin/env python3
"""
Example DeployBot Agent

This demonstrates how an agent would interact with the DeployBot Controller.
In production, this would actually execute deployments.
"""
import os
import sys
import time
import socket
import requests
import logging
from typing import Optional

# Configuration
CONTROLLER_URL = os.getenv("CONTROLLER_URL", "http://localhost:8080")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "5"))  # seconds
HOSTNAME = socket.gethostname()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("deploybot-agent")


class Agent:
    """DeployBot Agent"""
    
    def __init__(self, controller_url: str, hostname: str):
        self.controller_url = controller_url
        self.hostname = hostname
        self.agent_id: Optional[str] = None
        self.running = True
    
    def register(self) -> bool:
        """Register with controller"""
        try:
            response = requests.post(
                f"{self.controller_url}/v1/agents/register",
                json={
                    "hostname": self.hostname,
                    "capabilities": {
                        "platform": sys.platform,
                        "python_version": sys.version
                    }
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.agent_id = data["id"]
                logger.info(f"Registered successfully. Agent ID: {self.agent_id}")
                return True
            else:
                logger.error(f"Registration failed: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False
    
    def heartbeat(self) -> Optional[dict]:
        """Send heartbeat and receive job if available"""
        if not self.agent_id:
            logger.error("Not registered yet")
            return None
        
        try:
            response = requests.post(
                f"{self.controller_url}/v1/agents/{self.agent_id}/heartbeat",
                json={"status": "online"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("job")
            else:
                logger.error(f"Heartbeat failed: {response.status_code}")
                return None
        
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            return None
    
    def execute_job(self, job: dict):
        """Execute a deployment job"""
        job_id = job["id"]
        repo = job["repo"]
        ref = job["ref"]
        
        logger.info(f"Executing job {job_id}")
        logger.info(f"  Repo: {repo}")
        logger.info(f"  Ref: {ref}")
        logger.info(f"  Host: {job['host']}")
        
        # In a real implementation, this would:
        # 1. Clone/pull the repository
        # 2. Checkout the specified ref
        # 3. Run deployment scripts
        # 4. Report progress/logs to controller
        # 5. Update job status (success/failure)
        
        # Simulate deployment
        logger.info("Simulating deployment...")
        time.sleep(2)
        logger.info(f"Job {job_id} completed successfully!")
        
        # In production, you would report completion status back to the controller
        # via an API endpoint like POST /v1/jobs/{job_id}/status
    
    def run(self):
        """Main agent loop"""
        logger.info(f"Starting DeployBot Agent on {self.hostname}")
        logger.info(f"Controller: {self.controller_url}")
        
        # Register
        if not self.register():
            logger.error("Failed to register. Exiting.")
            return
        
        # Main loop
        logger.info("Starting heartbeat loop...")
        try:
            while self.running:
                # Send heartbeat
                job = self.heartbeat()
                
                # Execute job if received
                if job:
                    self.execute_job(job)
                else:
                    logger.debug("No jobs available")
                
                # Wait before next heartbeat
                time.sleep(HEARTBEAT_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
        
        except Exception as e:
            logger.error(f"Fatal error: {e}")


def main():
    """Main entry point"""
    agent = Agent(CONTROLLER_URL, HOSTNAME)
    agent.run()


if __name__ == "__main__":
    main()
