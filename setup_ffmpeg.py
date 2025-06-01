import os
import sys
import platform
import urllib.request
import zipfile
import tarfile
import shutil
from pathlib import Path

def download_file(url, filename):
    """Download a file from a URL."""
    print(f"Downloading {filename}...")
    urllib.request.urlretrieve(url, filename)
    print(f"Downloaded {filename}")

def extract_zip(zip_path, extract_to):
    """Extract a zip file."""
    print(f"Extracting {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    print(f"Extracted to {extract_to}")

def extract_tar(tar_path, extract_to):
    """Extract a tar file."""
    print(f"Extracting {tar_path}...")
    with tarfile.open(tar_path, 'r:gz') as tar_ref:
        tar_ref.extractall(extract_to)
    print(f"Extracted to {extract_to}")

def setup_ffmpeg():
    """Download and setup FFmpeg based on the platform."""
    # Create ffmpeg directory if it doesn't exist
    ffmpeg_dir = Path("ffmpeg")
    bin_dir = ffmpeg_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    system = platform.system().lower()
    machine = platform.machine().lower()
    
    # Map common architecture names
    arch_map = {
        'amd64': 'x86_64',
        'x86_64': 'x86_64',
        'x64': 'x86_64',
        'i386': 'x86',
        'x86': 'x86',
        'arm64': 'aarch64',
        'aarch64': 'aarch64'
    }
    
    # Map the architecture to our known values
    machine = arch_map.get(machine, machine)

    # FFmpeg download URLs
    urls = {
        'windows': {
            'x86_64': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
            'x86': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win32-gpl.zip'
        },
        'linux': {
            'x86_64': 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz',
            'aarch64': 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz'
        },
        'darwin': {
            'x86_64': 'https://evermeet.cx/ffmpeg/ffmpeg-6.1.zip',
            'aarch64': 'https://evermeet.cx/ffmpeg/ffmpeg-6.1.zip'
        }
    }

    # Get the appropriate URL
    if system not in urls:
        print(f"Unsupported system: {system}")
        sys.exit(1)

    if machine not in urls[system]:
        print(f"Unsupported architecture: {machine}")
        print(f"Available architectures for {system}: {list(urls[system].keys())}")
        sys.exit(1)

    url = urls[system][machine]
    filename = url.split('/')[-1]
    download_path = ffmpeg_dir / filename

    # Download FFmpeg
    download_file(url, download_path)

    # Extract the archive
    if filename.endswith('.zip'):
        extract_zip(download_path, ffmpeg_dir)
    elif filename.endswith('.tar.xz'):
        extract_tar(download_path, ffmpeg_dir)
    else:
        print(f"Unsupported archive format: {filename}")
        sys.exit(1)

    # Move FFmpeg binary to bin directory
    if system == 'windows':
        # Windows zip contains a directory with the binary
        extracted_dir = next(ffmpeg_dir.glob('ffmpeg-*'))
        shutil.move(str(extracted_dir / 'bin' / 'ffmpeg.exe'), str(bin_dir / 'ffmpeg.exe'))
    elif system == 'linux':
        # Linux tar contains the binary directly
        extracted_dir = next(ffmpeg_dir.glob('ffmpeg-*'))
        shutil.move(str(extracted_dir / 'ffmpeg'), str(bin_dir / 'ffmpeg'))
    elif system == 'darwin':
        # macOS zip contains the binary directly
        shutil.move(str(ffmpeg_dir / 'ffmpeg'), str(bin_dir / 'ffmpeg'))

    # Make the binary executable on Unix-like systems
    if system != 'windows':
        os.chmod(str(bin_dir / 'ffmpeg'), 0o755)

    # Clean up downloaded and extracted files
    download_path.unlink()
    if system == 'windows':
        shutil.rmtree(extracted_dir)
    elif system == 'linux':
        shutil.rmtree(extracted_dir)
    elif system == 'darwin':
        (ffmpeg_dir / 'ffmpeg').unlink()

    print("FFmpeg setup completed successfully!")

if __name__ == "__main__":
    setup_ffmpeg() 