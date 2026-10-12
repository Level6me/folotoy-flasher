from setuptools import setup, find_packages

setup(
    name="folotoy-flasher",
    version="1.0.0",
    description="Folotoy AI Passport 本地固件刷机 CLI 工具",
    author="Antigravity",
    packages=find_packages(),
    install_requires=[
        "esptool>=4.5.0",
        "pyserial>=3.5",
        "rich>=13.0.0",
        "click>=8.0.0",
        "requests>=2.28.0",
    ],
    entry_points={
        "console_scripts": [
            "folotoy-flasher=flasher.cli:cli",
        ],
    },
    python_requires=">=3.8",
)
