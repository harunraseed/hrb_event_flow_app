import os
import uuid
import base64
from werkzeug.utils import secure_filename
import requests
from urllib.parse import quote

class StorageManager:
    """GitHub-only storage for event logos"""
    
    def __init__(self, storage_type="github"):
        self.storage_type = "github"  # Force GitHub only
        self.github_repo = os.getenv('GITHUB_REPO', 'harunraseed/hrb_event_flow_app')
        self.github_branch = os.getenv('GITHUB_BRANCH', 'main')
        self.github_token = os.getenv('GITHUB_TOKEN')
        
        if not self.github_token:
            print("❌ WARNING: No GitHub token found. Logo uploads will fail.")
        else:
            print(f"✅ GitHub storage configured: {self.github_repo}")
        
    def save_image(self, image_file, folder="logos"):
        """Save image to GitHub and return the public URL"""
        try:
            if not image_file or not image_file.filename:
                print("❌ No image file provided")
                return None
            
            if not self.github_token:
                print("❌ No GitHub token configured")
                return None
            
            # Validate image first
            if not self._validate_image(image_file):
                return None
            
            # Generate unique filename
            file_extension = image_file.filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
            
            # Save to GitHub
            return self._save_to_github(image_file, folder, unique_filename)
                
        except Exception as e:
            print(f"❌ Error saving image: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _save_to_github(self, image_file, folder, filename):
        """Save image to GitHub repository"""
        try:
            print(f"🔄 Uploading {filename} to GitHub repository...")
            
            # Read file content
            file_content = image_file.read()
            image_file.seek(0)  # Reset file pointer
            
            # Encode to base64 for GitHub API
            content_b64 = base64.b64encode(file_content).decode('utf-8')
            
            # GitHub API path
            file_path = f"static/uploads/{folder}/{filename}"
            api_url = f"https://api.github.com/repos/{self.github_repo}/contents/{file_path}"
            
            # Prepare headers with proper authentication
            headers = {
                'Authorization': f'Bearer {self.github_token}',
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
                'Content-Type': 'application/json'
            }
            
            # Prepare data
            data = {
                'message': f'Add event logo: {filename}',
                'content': content_b64,
                'branch': self.github_branch
            }
            
            # Make request to GitHub API
            print(f"📤 Uploading to: {api_url}")
            response = requests.put(api_url, json=data, headers=headers, timeout=30)
            
            if response.status_code in [200, 201]:
                # Return the raw content URL
                raw_url = f"https://raw.githubusercontent.com/{self.github_repo}/{self.github_branch}/{file_path}"
                print(f"✅ Image uploaded successfully!")
                print(f"📁 File location: {file_path}")
                print(f"🔗 Public URL: {raw_url}")
                return raw_url
            else:
                print(f"❌ GitHub API Error:")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text}")
                if response.status_code == 403:
                    print(f"   🔐 Permission Error: Your GitHub token needs 'repo' scope permissions")
                    print(f"   📝 Go to GitHub → Settings → Developer settings → Personal access tokens")
                    print(f"   ✅ Create new token with 'repo' scope (full repository access)")
                elif response.status_code == 404:
                    print(f"   📂 Repository not found: {self.github_repo}")
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        print(f"   Message: {error_data['message']}")
                except:
                    pass
                return None
                
        except Exception as e:
            print(f"❌ Exception during GitHub upload: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    

    
    def _validate_image(self, image_file):
        """Validate image file type and size"""
        try:
            # Check file extension
            if not image_file.filename:
                return False
                
            allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
            file_extension = image_file.filename.rsplit('.', 1)[1].lower()
            
            if file_extension not in allowed_extensions:
                print(f"❌ Invalid file type: {file_extension}")
                return False
            
            # Check file size (max 10MB)
            image_file.seek(0, 2)  # Seek to end
            file_size = image_file.tell()
            image_file.seek(0)  # Reset to beginning
            
            max_size = 10 * 1024 * 1024  # 10MB
            if file_size > max_size:
                print(f"❌ File too large: {file_size/1024/1024:.1f}MB (max 10MB)")
                return False
                
            return True
            
        except Exception as e:
            print(f"❌ Error validating image: {e}")
            return False
    
    def delete_image(self, image_url):
        """Delete image from GitHub (future implementation)"""
        # GitHub deletion would require additional API call
        # For now, just return True since storage is cheap
        print("GitHub file deletion not implemented")
        return True