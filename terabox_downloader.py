import re
import json
import time
import logging
from urllib.parse import urlparse, unquote, parse_qs
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TeraboxDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
        
        # Common Terabox URL patterns
        self.patterns = {
            'share': r'https?://(?:www\.)?(?:terabox\.(?:com|app)|dubox\.com)/s/[a-zA-Z0-9_-]+',
            'file': r'https?://(?:www\.)?(?:terabox\.(?:com|app)|dubox\.com)/(?:sharing/link\?surl=|s/)[a-zA-Z0-9_-]+',
            'folder': r'https?://(?:www\.)?(?:terabox\.(?:com|app)|dubox\.com)/s/[a-zA-Z0-9_-]+\?pwd=[a-zA-Z0-9]+'
        }
    
    def extract_file_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract file information from Terabox URL"""
        try:
            logger.info(f"Processing URL: {url}")
            
            # Validate URL
            if not self.is_valid_terabox_url(url):
                return None
            
            # Send request to get page content
            response = self.session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            html_content = response.text
            
            # Try multiple extraction methods
            file_info = self._extract_from_json_ld(html_content)
            if not file_info:
                file_info = self._extract_from_meta_tags(html_content)
            if not file_info:
                file_info = self._extract_from_scripts(html_content)
            
            if file_info:
                # Generate filename if not found
                if 'filename' not in file_info:
                    timestamp = int(time.time())
                    file_info['filename'] = f"terabox_file_{timestamp}"
                
                # Get file size from headers if available
                if 'size' not in file_info and 'direct_url' in file_info:
                    try:
                        head_resp = self.session.head(
                            file_info['direct_url'], 
                            timeout=10,
                            allow_redirects=True
                        )
                        if 'Content-Length' in head_resp.headers:
                            file_info['size'] = int(head_resp.headers['Content-Length'])
                    except:
                        pass
                
                logger.info(f"Extracted info: {file_info}")
                return file_info
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting file info: {str(e)}")
            return None
    
    def _extract_from_json_ld(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract from JSON-LD structured data"""
        try:
            json_ld_pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([^<]+)</script>'
            matches = re.findall(json_ld_pattern, html, re.IGNORECASE)
            
            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, dict):
                        if 'name' in data:
                            return {
                                'filename': data.get('name', '').strip(),
                                'size': data.get('contentSize'),
                                'description': data.get('description', '').strip()
                            }
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.debug(f"JSON-LD extraction failed: {e}")
        
        return None
    
    def _extract_from_meta_tags(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract from meta tags"""
        try:
            info = {}
            
            # Look for OpenGraph tags
            og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html)
            if og_title:
                info['filename'] = unquote(og_title.group(1)).strip()
            
            # Look for file size
            size_match = re.search(r'["\']size["\']\s*:\s*["\']?(\d+)["\']?', html)
            if size_match:
                info['size'] = int(size_match.group(1))
            
            # Look for download URL
            download_match = re.search(r'["\'](?:download_)?url["\']\s*:\s*["\']([^"\']+)["\']', html)
            if download_match:
                info['direct_url'] = download_match.group(1)
            
            return info if info else None
            
        except Exception as e:
            logger.debug(f"Meta tag extraction failed: {e}")
            return None
    
    def _extract_from_scripts(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract from JavaScript variables"""
        try:
            info = {}
            
            # Common Terabox JavaScript patterns
            patterns = {
                'filename': r'file_name\s*[=:]\s*["\']([^"\']+)["\']',
                'size': r'file_size\s*[=:]\s*(\d+)',
                'url': r'(?:downloadUrl|file_url)\s*[=:]\s*["\']([^"\']+)["\']',
                'md5': r'file_md5\s*[=:]\s*["\']([^"\']+)["\']'
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    info[key] = match.group(1)
            
            return info if info else None
            
        except Exception as e:
            logger.debug(f"Script extraction failed: {e}")
            return None
    
    def is_valid_terabox_url(self, url: str) -> bool:
        """Check if URL is a valid Terabox URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Check domain
            valid_domains = ['terabox.com', 'www.terabox.com', 'terabox.app', 
                           'dubox.com', 'www.dubox.com']
            
            if any(domain.endswith(d) for d in valid_domains):
                # Check path patterns
                path = parsed.path
                if '/s/' in path or '/sharing/' in path:
                    return True
            
            return False
            
        except:
            return False
    
    def get_direct_download_url(self, url: str) -> Optional[str]:
        """Try to get direct download URL"""
        try:
            file_info = self.extract_file_info(url)
            if file_info and 'direct_url' in file_info:
                return file_info['direct_url']
            
            # Alternative: Try to find download link in page
            response = self.session.get(url, timeout=30)
            download_patterns = [
                r'href=["\'](https?://[^"\']+?\.(?:mp4|avi|mkv|mp3|pdf|zip)[^"\']*)["\']',
                r'downloadLink\s*=\s*["\']([^"\']+)["\']',
                r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in download_patterns:
                matches = re.findall(pattern, response.text, re.IGNORECASE)
                for match in matches:
                    if match and ('http' in match or '//' in match):
                        return match if isinstance(match, str) else match[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting direct URL: {str(e)}")
            return None