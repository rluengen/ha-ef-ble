"""
EcoFlow cloud client for the certificate/token BLE auth.

Power Kit / "Space" devices (Power Hub, etc.) don't use the legacy
``md5(userId + serial)`` BLE auth. Instead the device emits a signed challenge and
the app fetches a per-device bind blob (``randomCode`` + ``userInfoEn``) from the
EcoFlow cloud, then relays it to the device over BLE (``RefreshToken``). The
``userInfoEn`` is produced and signed by the cloud - we only relay it.

The bind call mirrors the app (Retrofit interface ``Lw4/b;``, consumed by
``BleAuthOMOSHelper``). The consumer app (package ``com.ecoflow``) uses the
normal-user path; the installer/Pro app (``com.ecoflow.pro``) uses the
enterprise path. Both return ``BaseResponse<BindResponseBean{randomCode,
userInfoEn}>``. We try the consumer path first and fall back to the enterprise
path so a single connect attempt reveals which one the cloud serves for a SN.
"""

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Reverse-engineered from BleAuthOMOSHelper -> w4.b (Retrofit), confirmed by a raw
# DEX annotation parse:
#   R2: GET /iot-service/user/device/refreshToken?sn=<SN>   (consumer app path)
#   i5: GET /iot-service/enterprise-device?sn=<SN>          (installer/Pro app path)
# both -> BaseResponse<BindResponseBean{ randomCode, userInfoEn }>
BLE_BIND_DATA_PATH = "/iot-service/user/device/refreshToken"
BLE_BIND_DATA_PATH_ENTERPRISE = "/iot-service/enterprise-device"


def _normalize_token(token: Any) -> str:
    """
    Return a bearer token string from whatever ``/auth/login`` handed us.

    The app reads ``resultObject.getString("access_token")``; depending on the
    response shape our login helper may have captured the raw JWT string or a
    nested object (e.g. ``{"access_token": ..., "refresh_token": ...}``). Coerce
    both to the JWT string so the ``Authorization`` header is well-formed.
    """
    if isinstance(token, str):
        return token
    if isinstance(token, dict):
        for key in ("access_token", "token", "accessToken"):
            value = token.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _mask(token: str) -> str:
    """Mask a token for logging (show length + a few edge chars only)."""
    if not token:
        return "<empty>"
    if len(token) <= 12:
        return f"<len={len(token)}>"
    return f"{token[:6]}...{token[-4:]} <len={len(token)}>"


@dataclass(frozen=True)
class BleBindData:
    """Per-device BLE bind blob returned by the cloud, relayed to the device."""

    random_code: str
    user_info_en: str


class EcoFlowCloud:
    """Authenticated EcoFlow IoT cloud client (Bearer access token)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        access_token: Any,
    ) -> None:
        self._session = session
        self._base_url = base_url
        self._access_token = _normalize_token(access_token)
        if not self._access_token:
            _LOGGER.error(
                "EcoFlowCloud: no usable access token (got %s); the Authorization "
                "header will be empty - reconfigure the integration via EcoFlow login",
                type(access_token).__name__,
            )
        elif not isinstance(access_token, str):
            _LOGGER.warning(
                "EcoFlowCloud: access token was %s, not a string; normalized to a "
                "bearer string",
                type(access_token).__name__,
            )

    def _headers(self) -> dict[str, str]:
        # The app adds the bearer token via HttpHeaderInterceptor; the other headers
        # mirror the standard app request headers.
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "lang": "en",
            "platform": "android",
        }

    async def _fetch_bind(self, path: str, sn: str) -> BleBindData | None:
        """GET one bind endpoint; return bind data on success, else log + None."""
        url = f"https://{self._base_url}{path}"
        _LOGGER.info(
            "get_ble_bind_data: GET %s?sn=%s (token=%s)",
            url,
            sn,
            _mask(self._access_token),
        )
        try:
            async with self._session.get(
                url, params={"sn": sn}, headers=self._headers()
            ) as response:
                status = response.status
                body = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("get_ble_bind_data: request to %s failed: %s", url, err)
            return None
        except ValueError as err:
            _LOGGER.error("get_ble_bind_data: %s returned non-JSON: %s", url, err)
            return None

        code = str(body.get("code"))
        if code != "0":
            _LOGGER.error(
                "get_ble_bind_data: %s -> http=%s code=%s message=%s body=%s",
                path,
                status,
                body.get("code"),
                body.get("message"),
                body,
            )
            return None

        data = body.get("data") or {}
        random_code = data.get("randomCode")
        user_info_en = data.get("userInfoEn")
        if not random_code or not user_info_en:
            _LOGGER.error(
                "get_ble_bind_data: %s ok but missing randomCode/userInfoEn: %s",
                path,
                data,
            )
            return None

        _LOGGER.info("get_ble_bind_data: %s succeeded (randomCode present)", path)
        return BleBindData(random_code=random_code, user_info_en=user_info_en)

    async def get_ble_bind_data(self, sn: str) -> BleBindData | None:
        """
        Fetch the per-device BLE bind blob (randomCode + userInfoEn).

        Tries the consumer endpoint first, then the enterprise endpoint, so the
        first live connect reveals which one the cloud serves for this device.
        """
        for path in (BLE_BIND_DATA_PATH, BLE_BIND_DATA_PATH_ENTERPRISE):
            bind = await self._fetch_bind(path, sn)
            if bind is not None:
                return bind
        return None
