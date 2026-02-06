from pydantic import BaseModel, Field

class FileReference(BaseModel):
    file_path: str = Field(..., description="Workspace-relative path (under BASE_DIR), using forward slashes.")
    agent_type: str = Field(..., description="Agent type that produced the file (e.g., 'ProductSpecAgent').")
    description: str = Field(..., description="What the file contains and why it matters (1–3 sentences).")
    source: str = Field(..., description="Producer identifier for retrieval/debug (typically agent_instance_plan.instance_id).")
