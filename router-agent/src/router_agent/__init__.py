"""OpenWrt AI Copilot — on-device router agent.

Sprint 3 scope: **data collection only**. The agent connects to a router over
SSH (or runs locally, optionally via LuCI RPC), gathers CPU, RAM, temperature,
storage, network, firewall, WiFi, clients, ARP, routing, VPN, DHCP, packages,
kernel, and logs, and returns ONE normalized JSON snapshot. There is no AI and
no dashboard.
"""

__version__ = "0.1.0"
