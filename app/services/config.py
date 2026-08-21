"""
novel2drama services 配置
集中管理 LLM / GPU Gateway / 存储路径
"""
import os

# ============ LLM 配置 (smmmc) ============
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.smmmc.cn/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")  # 必须设置
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-pro")  # 默认走 smmmc 主力模型
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))

# ============ GPU Gateway 配置 ============
# 指向 GPU 服务器的 OpenAI 兼容网关 (gpu-gateway)
GPU_GATEWAY_BASE_URL = os.getenv("GPU_GATEWAY_BASE_URL", "http://36.138.26.41:16000")
GPU_GATEWAY_KEY = os.getenv("GPU_GATEWAY_KEY", "gfw-h3-zimg-qwen-local")
GPU_GATEWAY_TIMEOUT = int(os.getenv("GPU_GATEWAY_TIMEOUT", "600"))  # 长推理

# 模型名映射 (网关侧注册的名字)
Z_IMAGE_MODEL = os.getenv("Z_IMAGE_MODEL", "z-image-turbo")
H3_MODEL = os.getenv("H3_MODEL", "minimax-h3")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.8-27b-awq")

# ============ 存储配置 ============
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
PROJECTS_DATA_DIR = os.path.join(DATA_DIR, "projects")
os.makedirs(PROJECTS_DATA_DIR, exist_ok=True)

# 各子目录
def project_dir(project_id: str) -> str:
    d = os.path.join(PROJECTS_DATA_DIR, project_id)
    os.makedirs(d, exist_ok=True)
    return d

def project_subdir(project_id: str, sub: str) -> str:
    """sub: novels/storyboard/assets/characters/assets/scenes/keyframes/h3_segments/exports/temp"""
    d = os.path.join(project_dir(project_id), sub)
    os.makedirs(d, exist_ok=True)
    return d

# ============ Worker 配置 ============
WORKER_POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))  # 秒
WORKER_MAX_RETRIES = int(os.getenv("WORKER_MAX_RETRIES", "1"))

# ============ Agent 配置 ============
AGENT_MAX_PATCH_OPS = int(os.getenv("AGENT_MAX_PATCH_OPS", "50"))
