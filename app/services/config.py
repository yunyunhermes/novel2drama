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

# xDiT H3 高画质服务 (默认本机双卡服务)
XDIT_H3_BASE_URL = os.getenv("XDIT_H3_BASE_URL", "http://127.0.0.1:15100")
XDIT_H3_TIMEOUT = int(os.getenv("XDIT_H3_TIMEOUT", "1800"))
H3_QUALITY = os.getenv("H3_QUALITY", "preview").lower()
H3_PREVIEW_SIZE = os.getenv("H3_PREVIEW_SIZE", "512x512")
H3_HIGH_SIZE = os.getenv("H3_HIGH_SIZE", "768x768")

# 模型名映射 (网关侧注册的名字)
Z_IMAGE_MODEL = os.getenv("Z_IMAGE_MODEL", "z-image-turbo")
H3_MODEL = os.getenv("H3_MODEL", "minimax-h3")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.8-27b-awq")

# ============ Image2 资产生成配置 (smmmc gpt-image-2) ============
# 资产图统一走 image2 (不再用 Z-Image 出资产图); Z-Image 仅保留段首图关键帧。
# KEY 优先取 SMMMC_API_KEY, 回退 LLM_API_KEY (GPU 侧 /etc/novel2drama.env 只有 LLM_API_KEY, 两者同值)。
IMAGE2_BASE_URL = os.getenv("IMAGE2_BASE_URL", "https://api.smmmc.cn/v1")
IMAGE2_API_KEY = os.getenv("SMMMC_API_KEY", os.getenv("IMAGE2_API_KEY", os.getenv("LLM_API_KEY", "")))
IMAGE2_MODEL = os.getenv("IMAGE2_MODEL", "gpt-image-2")
IMAGE2_QUALITY = os.getenv("IMAGE2_QUALITY", "high")
IMAGE2_RESOLUTION = os.getenv("IMAGE2_RESOLUTION", "2K")
IMAGE2_TIMEOUT = int(os.getenv("IMAGE2_TIMEOUT", "300"))
# 资产生成默认画幅 (图片渠道传比例字符串; 角色多视角例外为16:9, 见 asset_pipeline)
ASSET_DEFAULT_ASPECT = os.getenv("ASSET_DEFAULT_ASPECT", "4:3")

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
# 并发消费线程数 (默认=GPU卡数, 匹配双卡; 多任务并行触发 gateway, GPU 各跑一个)
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "2"))

# ============ Agent 配置 ============
AGENT_MAX_PATCH_OPS = int(os.getenv("AGENT_MAX_PATCH_OPS", "50"))
