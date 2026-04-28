# Start All MCP Servers for FounderFlow Backend
# Run this script to start all 6 MCP servers in separate PowerShell windows

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Starting FounderFlow MCP Servers..." -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# Activate virtual environment path
$venvPath = "d:\FounderFlow\backend\venv\Scripts\Activate.ps1"

# Start Instagram Server (Port 8000)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$venvPath'; cd 'd:\FounderFlow\backend'; python servers\instagram_server.py" -WindowStyle Normal
Write-Host "✓ Instagram Server starting on port 8000..." -ForegroundColor Green
Start-Sleep -Milliseconds 500

# Start Email Server (Port 8001)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$venvPath'; cd 'd:\FounderFlow\backend'; python servers\email_server.py" -WindowStyle Normal
Write-Host "✓ Email Server starting on port 8001..." -ForegroundColor Green
Start-Sleep -Milliseconds 500

# Start Meet Schedule Server (Port 8002)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$venvPath'; cd 'd:\FounderFlow\backend'; python servers\meet_schedule_server.py" -WindowStyle Normal
Write-Host "✓ Meet Schedule Server starting on port 8002..." -ForegroundColor Green
Start-Sleep -Milliseconds 500

# Start LinkedIn Server (Port 8003)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$venvPath'; cd 'd:\FounderFlow\backend'; python servers\linkedIn_Mcpserver.py" -WindowStyle Normal
Write-Host "✓ LinkedIn Server starting on port 8003..." -ForegroundColor Green
Start-Sleep -Milliseconds 500

# Start Hiring Server (Port 8004)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$venvPath'; cd 'd:\FounderFlow\backend'; python servers\hiring_server.py" -WindowStyle Normal
Write-Host "✓ Hiring Server starting on port 8004..." -ForegroundColor Green
Start-Sleep -Milliseconds 500

# Start Lead Gen Server (Port 8006) - Note: using -m for package execution
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$venvPath'; cd 'd:\FounderFlow\backend'; python -m servers.lead_gen.lead_gen_server" -WindowStyle Normal
Write-Host "✓ Lead Gen Server starting on port 8006..." -ForegroundColor Green

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "All servers launched!" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "Server Status:" -ForegroundColor Yellow
Write-Host "  Instagram     → http://localhost:8000/mcp" -ForegroundColor White
Write-Host "  Email         → http://localhost:8001/mcp" -ForegroundColor White
Write-Host "  Meet Schedule → http://localhost:8002/mcp" -ForegroundColor White
Write-Host "  LinkedIn      → http://localhost:8003/mcp" -ForegroundColor White
Write-Host "  Hiring        → http://localhost:8004/mcp" -ForegroundColor White
Write-Host "  Lead Gen      → http://localhost:8006/mcp" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C in each window to stop individual servers" -ForegroundColor Yellow
