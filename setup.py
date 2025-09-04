#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="audio-splitter-pro",
    version="2.0.0",
    description="Professional audio routing and compression tool for Linux",
    author="Brandon",
    author_email="brandon@example.com",
    py_modules=["audio_splitter_gui_v2"],
    install_requires=[
        "tomli>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "audio-splitter-pro=audio_splitter_gui_v2:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Sound/Audio",
    ],
)
