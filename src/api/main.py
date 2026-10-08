import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        workers=1,
    )


if __name__ == "__main__":
    main()
