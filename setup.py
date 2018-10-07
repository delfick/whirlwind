from whirlwind import VERSION

from setuptools import setup, find_packages

setup(
      name = "whirlwind-web"
    , version = VERSION
    , packages = ['whirlwind'] + ['whirlwind.%s' % pkg for pkg in find_packages('whirlwind')]
    , include_package_data = True

    , install_requires =
      [ "tornado >= 5.1.1"
      , "option_merge >= 1.6"
      , "input_algorithms >= 0.6.0"
      ]

    , extras_require =
      { "tests":
        [ "noseOfYeti>=1.7"
        , "asynctest==0.10.0"
        , "nose"
        , "mock"
        ]
      , "peer":
        [ "tornado==5.1.1"
        , "option_merge==1.6"
        , "input_algorithms==0.6.0"
        ]
      }

    # metadata for upload to PyPI
    , url = "http://github.com/delfick/whirlwind"
    , author = "Stephen Moore"
    , author_email = "delfick755@gmail.com"
    , description = "Wrapper around the tornado web server library"
    , license = "MIT"
    , keywords = "tornado web"
    )
