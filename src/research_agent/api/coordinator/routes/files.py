"""File upload endpoints for coordinator agent."""

from fastapi import APIRouter, UploadFile, File, HTTPException, status
from pydantic import BaseModel
from typing import List
import uuid
import os
from pathlib import Path
import mimetypes

router = APIRouter(prefix="/api/coordinator", tags=["coordinator-files"])


# Allowed file types (images and common document formats)
ALLOWED_MIME_TYPES = {
    # Images
    "image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp",
    # Documents
    "application/pdf",
    "text/plain", "text/markdown",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Data
    "text/csv",
    "application/json",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# File storage directory
UPLOAD_DIR = Path("uploads/coordinator")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class FileUploadResponse(BaseModel):
    """Response after successful file upload."""
    file_id: str
    filename: str
    mime_type: str
    size: int
    url: str


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Upload a file for use in messages.
    
    Args:
        file: The file to upload
        
    Returns:
        File metadata including URL for referencing in messages
        
    Raises:
        HTTPException: If file type not allowed or file too large
    """
    # Check file size
    content = await file.read()
    file_size = len(content)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # Determine MIME type
    mime_type = file.content_type
    if not mime_type:
        mime_type, _ = mimetypes.guess_type(file.filename or "")
    
    # Check if file type is allowed
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{mime_type}' not allowed. Supported types: images, PDF, text, CSV, JSON"
        )
    
    # Generate unique file ID
    file_id = str(uuid.uuid4())
    
    # Get file extension
    ext = Path(file.filename or "file").suffix
    if not ext and mime_type:
        ext = mimetypes.guess_extension(mime_type) or ""
    
    # Save file
    file_path = UPLOAD_DIR / f"{file_id}{ext}"
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Generate URL (relative path for now)
    file_url = f"/uploads/coordinator/{file_id}{ext}"
    
    return FileUploadResponse(
        file_id=file_id,
        filename=file.filename or f"file{ext}",
        mime_type=mime_type or "application/octet-stream",
        size=file_size,
        url=file_url,
    )


@router.post("/upload/multiple", response_model=List[FileUploadResponse])
async def upload_multiple_files(files: List[UploadFile] = File(...)):
    """Upload multiple files at once.
    
    Args:
        files: List of files to upload
        
    Returns:
        List of file metadata
    """
    if len(files) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 files per upload"
        )
    
    responses = []
    for file in files:
        response = await upload_file(file)
        responses.append(response)
    
    return responses
