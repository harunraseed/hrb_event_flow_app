import os
import uuid
import base64
from werkzeug.utils import secure_filename
import requests
from urllib.parse import quote

# Content type mapping
CONTENT_TYPES = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp',
}


class StorageManager:
    """Image storage manager with Supabase Storage (primary) and GitHub (fallback).
    
    Set STORAGE_TYPE=supabase in .env and provide SUPABASE_URL + SUPABASE_SERVICE_KEY.
    Falls back to GitHub storage if Supabase is not configured.
    """
    
    BUCKET_NAME = 'event-assets'
    
    def __init__(self):
        self.storage_type = os.getenv('STORAGE_TYPE', 'supabase').lower()
        
        # Supabase config
        self.supabase_url = os.getenv('SUPABASE_URL', '').rstrip('/')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_KEY', '')
        
        # GitHub fallback config
        self.github_repo = os.getenv('GITHUB_REPO', '')
        self.github_branch = os.getenv('GITHUB_BRANCH', 'main')
        self.github_token = os.getenv('GITHUB_TOKEN', '')
        
        # Auto-detect best available storage
        if self.storage_type == 'supabase' and self.supabase_url and self.supabase_key:
            self.storage_type = 'supabase'
            print(f"✅ Supabase Storage configured: {self.supabase_url}")
            self._ensure_bucket()
        elif self.github_token and self.github_repo:
            self.storage_type = 'github'
            print(f"✅ GitHub storage configured: {self.github_repo}")
        else:
            self.storage_type = 'none'
            print("⚠️ WARNING: No storage configured. Image uploads will fail.")
            print("   Set SUPABASE_URL + SUPABASE_SERVICE_KEY (recommended)")
            print("   Or set GITHUB_TOKEN + GITHUB_REPO (fallback)")
    
    # ──────────────────────────────────────────────
    # Public API (same interface for all backends)
    # ──────────────────────────────────────────────
    
    def save_image(self, image_file, folder="logos"):
        """Save image and return the public URL."""
        try:
            if not image_file or not image_file.filename:
                return None
            
            if not self._validate_image(image_file):
                return None
            
            file_extension = image_file.filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
            
            if self.storage_type == 'supabase':
                return self._save_to_supabase(image_file, folder, unique_filename)
            elif self.storage_type == 'github':
                return self._save_to_github(image_file, folder, unique_filename)
            else:
                print("❌ No storage backend configured")
                return None
                
        except Exception as e:
            print(f"❌ Error saving image: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def delete_image(self, image_url):
        """Delete image by its public URL."""
        try:
            if not image_url:
                return False
            
            if self.storage_type == 'supabase':
                return self._delete_from_supabase(image_url)
            else:
                print("Image deletion not implemented for this storage backend")
                return True
                
        except Exception as e:
            print(f"❌ Error deleting image: {e}")
            return False
    
    # ──────────────────────────────────────────────
    # Supabase Storage
    # ──────────────────────────────────────────────
    
    def _ensure_bucket(self):
        """Create the storage bucket if it doesn't exist, or ensure it's public."""
        try:
            url = f"{self.supabase_url}/storage/v1/bucket/{self.BUCKET_NAME}"
            headers = self._supabase_headers()
            
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                # Bucket exists — ensure it's public
                data = resp.json()
                if not data.get('public', False):
                    update_resp = requests.put(
                        url,
                        json={'public': True, 'file_size_limit': 10 * 1024 * 1024,
                              'allowed_mime_types': list(CONTENT_TYPES.values())},
                        headers=self._supabase_headers(content_type='application/json'),
                        timeout=10
                    )
                    if update_resp.status_code == 200:
                        print(f"✅ Updated bucket '{self.BUCKET_NAME}' to public")
                return
            
            # Create bucket (public so images are accessible via URL)
            create_url = f"{self.supabase_url}/storage/v1/bucket"
            data = {
                'id': self.BUCKET_NAME,
                'name': self.BUCKET_NAME,
                'public': True,
                'file_size_limit': 10 * 1024 * 1024,  # 10MB
                'allowed_mime_types': list(CONTENT_TYPES.values())
            }
            resp = requests.post(create_url, json=data, headers=headers, timeout=10)
            if resp.status_code in [200, 201]:
                print(f"✅ Created storage bucket: {self.BUCKET_NAME}")
            elif resp.status_code == 409:
                pass  # Already exists
            else:
                print(f"⚠️ Bucket creation response: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"⚠️ Could not verify storage bucket: {e}")
    
    def _supabase_headers(self, content_type=None):
        """Build auth headers for Supabase Storage REST API."""
        headers = {
            'Authorization': f'Bearer {self.supabase_key}',
            'apikey': self.supabase_key,
        }
        if content_type:
            headers['Content-Type'] = content_type
        return headers
    
    def _save_to_supabase(self, image_file, folder, filename):
        """Upload file to Supabase Storage and return public URL."""
        try:
            file_path = f"{folder}/{filename}"
            file_content = image_file.read()
            image_file.seek(0)
            
            file_ext = filename.rsplit('.', 1)[1].lower()
            content_type = CONTENT_TYPES.get(file_ext, 'application/octet-stream')
            
            url = f"{self.supabase_url}/storage/v1/object/{self.BUCKET_NAME}/{file_path}"
            headers = self._supabase_headers(content_type=content_type)
            
            resp = requests.post(url, data=file_content, headers=headers, timeout=30)
            
            if resp.status_code in [200, 201]:
                public_url = f"{self.supabase_url}/storage/v1/object/public/{self.BUCKET_NAME}/{file_path}"
                print(f"✅ Uploaded to Supabase: {file_path}")
                return public_url
            else:
                print(f"❌ Supabase upload failed: {resp.status_code} {resp.text}")
                return None
                
        except Exception as e:
            print(f"❌ Supabase upload error: {e}")
            return None
    
    def _delete_from_supabase(self, image_url):
        """Delete file from Supabase Storage by its public URL."""
        try:
            # Extract path from URL: .../object/public/event-assets/logos/abc.jpg → logos/abc.jpg
            marker = f"/object/public/{self.BUCKET_NAME}/"
            if marker not in image_url:
                print(f"⚠️ URL doesn't match Supabase pattern: {image_url}")
                return False
            
            file_path = image_url.split(marker)[1]
            
            url = f"{self.supabase_url}/storage/v1/object/{self.BUCKET_NAME}"
            headers = self._supabase_headers(content_type='application/json')
            data = {'prefixes': [file_path]}
            
            resp = requests.delete(url, json=data, headers=headers, timeout=10)
            if resp.status_code in [200, 204]:
                print(f"✅ Deleted from Supabase: {file_path}")
                return True
            else:
                print(f"⚠️ Supabase delete response: {resp.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Supabase delete error: {e}")
            return False
    
    # ──────────────────────────────────────────────
    # GitHub Storage (fallback)
    # ──────────────────────────────────────────────
    
    def _save_to_github(self, image_file, folder, filename):
        """Save image to GitHub repository."""
        try:
            file_content = image_file.read()
            image_file.seek(0)
            content_b64 = base64.b64encode(file_content).decode('utf-8')
            
            file_path = f"static/uploads/{folder}/{filename}"
            api_url = f"https://api.github.com/repos/{self.github_repo}/contents/{file_path}"
            
            headers = {
                'Authorization': f'Bearer {self.github_token}',
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            }
            data = {
                'message': f'Add asset: {filename}',
                'content': content_b64,
                'branch': self.github_branch,
            }
            
            resp = requests.put(api_url, json=data, headers=headers, timeout=30)
            
            if resp.status_code in [200, 201]:
                raw_url = f"https://raw.githubusercontent.com/{self.github_repo}/{self.github_branch}/{file_path}"
                print(f"✅ Uploaded to GitHub: {file_path}")
                return raw_url
            else:
                print(f"❌ GitHub upload failed: {resp.status_code} {resp.text}")
                return None
                
        except Exception as e:
            print(f"❌ GitHub upload error: {e}")
            return None
    
    # ──────────────────────────────────────────────
    # Validation
    # ──────────────────────────────────────────────
    
    def _validate_image(self, image_file):
        """Validate image file type and size."""
        try:
            if not image_file.filename:
                return False
            
            if '.' not in image_file.filename:
                print("❌ File has no extension")
                return False
                
            file_extension = image_file.filename.rsplit('.', 1)[1].lower()
            if file_extension not in CONTENT_TYPES:
                print(f"❌ Invalid file type: {file_extension}")
                return False
            
            image_file.seek(0, 2)
            file_size = image_file.tell()
            image_file.seek(0)
            
            if file_size > 10 * 1024 * 1024:
                print(f"❌ File too large: {file_size / 1024 / 1024:.1f}MB (max 10MB)")
                return False
                
            return True
            
        except Exception as e:
            print(f"❌ Validation error: {e}")
            return False