1. Configure VirtualBox Adapter 2
- Shut down Ubuntu VM.
- VirtualBox → Settings → Network → Adapter 2
- Check Enable Network Adapter.
- Attached to: Host-only Adapter
- Name: VirtualBox Host-Only Ethernet Adapter
- Click OK and start Ubuntu.
2. Find IP addresses
Ubuntu:
hostname -I


Windows PowerShell:
ipconfig


Look for the VirtualBox Host-Only adapter. My Example:
- Windows: 192.168.56.1
- Ubuntu: 192.168.56.101
3. Enable SSH on Ubuntu
sudo apt install openssh-server
sudo systemctl enable --now ssh


4. Generate SSH key on Windows
ssh-keygen -t ed25519 -f "$HOME\.ssh\id_ed25519"
Get-Content "$HOME\.ssh\id_ed25519.pub"


5. Authorize key on Ubuntu
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys


Paste the Windows public key, save, then:
chmod 600 ~/.ssh/authorized_keys


6. Test SSH from Windows
ssh seed@192.168.56.101


Replace the username and IP as needed.
7. Run project in Windows PowerShell
python -m pip install paramiko
docker compose up -d
$env:SSH_HOST="192.168.56.101"
$env:SSH_USER="seed"
python ssh_monitor.py
python -m uvicorn main:app --reload
