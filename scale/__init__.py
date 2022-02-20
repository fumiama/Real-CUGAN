import azure.functions as func

from numpy import frombuffer, uint8
from cv2 import imencode, imdecode, IMREAD_UNCHANGED
from urllib.request import unquote
from urllib3 import PoolManager
from time import time
from os.path import exists
from .upcunet_v3 import RealWaifuUpScaler

pool = PoolManager()
ups = {}

last_req_time = 0
def clear_pool() -> None:
    global pool, last_req_time
    if time() - last_req_time > 60:
        pool.clear()
        last_req_time = time()

# frame, result is all cv2 image
def calc(model: str, scale: int, tile: int, frame):
    m = f"{model}_{tile}"
    if m in ups: m = ups[m]
    else:
        ups[m] = RealWaifuUpScaler(scale, model, half=False, device="cpu:0")
        m = ups[m]
    img = m(frame, tile_mode=tile)[:, :, ::-1]
    del frame
    return img

# data is image data, result is cv2 image
# data will be deleted
def calcdata(model: str, scale: int, tile: int, data: bytes):
    umat = frombuffer(data, uint8)
    del data
    frame = imdecode(umat, IMREAD_UNCHANGED)[:, :, [2, 1, 0]]
    del umat
    return calc(model, scale, tile, frame)

MODEL_LIST = ["conservative", "no-denoise", "denoise1x", "denoise2x", "denoise3x"]

def main(req: func.HttpRequest) -> func.HttpResponse:
    model = req.params.get("model")
    scale = req.params.get("scale")
    tile = req.params.get("tile")

    if model == None: model = "no-denoise"
    if scale == None: scale = "2"
    if tile == None: tile = "2"
    scale = int(scale)
    tile = int(tile)

    if model not in MODEL_LIST: return func.HttpResponse("400 BAD REQUEST: no such model", status_code=400)
    if scale not in [2, 3, 4]: return func.HttpResponse("400 BAD REQUEST: no such scale", status_code=400)
    if tile not in range(9): return func.HttpResponse("400 BAD REQUEST: no such tile", status_code=400)

    model = f"weights_v3/up{scale}x-latest-{model}.pth"
    if not exists(model): return func.HttpResponse("400 BAD REQUEST: no such model", status_code=400)

    if req.method == 'GET':
        url = req.params.get("url")
        if url == None: return func.HttpResponse("400 BAD REQUEST: no url", status_code=400)
        url = unquote(url)
        global pool
        clear_pool()
        r = pool.request('GET', url)
        data = r.data
        r.release_conn()
        del r
    else: data = req.get_body()

    if not len(data): return func.HttpResponse("400 BAD REQUEST: zero data len", status_code=400)
    _, data = imencode(".webp", calcdata(model, scale, tile, data))
    data = data.tobytes()
    if not len(data): return func.HttpResponse("500 Internal Server Error: zero output data len", status_code=500)
    return func.HttpResponse(data, mimetype="image/webp")
