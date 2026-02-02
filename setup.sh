#!/bin/bash
# Setup script for Travian AI Assistant

echo "=========================================="
echo "Travian AI Assistant Setup"
echo "=========================================="

# Check Python version
python3 --version
if [ $? -ne 0 ]; then
    echo "Error: Python 3 is required but not found"
    exit 1
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file..."
    cp .env.example .env
    echo "✓ Created .env file - please edit it with your credentials"
else
    echo ""
    echo "✓ .env file already exists"
fi

# Create directories
echo ""
echo "Creating directories..."
mkdir -p screenshots
mkdir -p session_data

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your Travian credentials:"
echo "   nano .env"
echo ""
echo "2. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "3. Run the bot:"
echo "   python bot.py"
echo ""
echo "⚠️  IMPORTANT: Using automation bots may violate"
echo "   Travian's Terms of Service. Use at your own risk!"
echo ""
