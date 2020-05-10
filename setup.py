from whirlwind import VERSION

from setuptools import setup, find_packages

# fmt: off

setup(
      name = "whirlwind-web"
    , version = VERSION
    , packages = ['whirlwind'] + ['whirlwind.%s' % pkg for pkg in find_packages('whirlwind')]
    , include_package_data = True

    , install_requires =
      [ "tornado >= 5.1.1"
      , "delfick_project >= 0.5"
      ]

    , extras_require =
      { "tests":
        [ "noseOfYeti==2.0.1"
        , "asynctest==0.13.0"
        , "pytest==5.3.1"
        , "alt-pytest-asyncio==0.5.2"
        ]
      , "peer":
        [ "tornado==5.1.1"
        , "delfick_project==0.5"
        ]
      }

    , entry_points =
      { 'console_scripts' :
        [ 'run_whirlwind_pytest = whirlwind.test_helpers:run_pytest'
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
