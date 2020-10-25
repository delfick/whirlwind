from setuptools import setup, find_packages
import runpy
import os

version = runpy.run_path(os.path.join(os.path.dirname(__file__), "whirlwind", "version.py"))

# fmt: off

setup(
      name = "whirlwind-web"
    , version = version["VERSION"]
    , packages = find_packages(include="whirlwind.*", exclude=["tests*"])

    , install_requires =
      [ "tornado >= 5.1.1"
      , "delfick_project >= 0.5"
      ]

    , extras_require =
      { "tests":
        [ "noseOfYeti==2.0.1"
        , "mock==4.0.2"
        , "pytest==5.3.1"
        , "aiohttp==3.7.0"
        , "alt-pytest-asyncio==0.5.3"
        , "pytest-helpers-namespace==2019.1.8"
        ]
      , "peer":
        [ "tornado==5.1.1"
        , "delfick_project==0.5"
        ]
      }

    , entry_points =
      { 'console_scripts' :
        [ 'run_whirlwind_pytest = whirlwind._pytest:run_pytest'
        ]
      }

    # metadata for upload to PyPI
    , url = "http://github.com/delfick/whirlwind"
    , author = "Stephen Moore"
    , author_email = "delfick755@gmail.com"
    , description = "Wrapper around the tornado web server library"
    , long_description = open("README.rst").read()
    , license = "MIT"
    , keywords = "tornado web"
    )

# fmt: on
