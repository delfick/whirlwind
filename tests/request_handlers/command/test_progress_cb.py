# coding: spec

from whirlwind.request_handlers.command import ProgressMessageMaker

from unittest import TestCase, mock

describe TestCase, "ProgressMessageMaker":
    it "can get a logger name":
        maker = ProgressMessageMaker()
        assert maker.logger_name == "tests.request_handlers.command.test_progress_cb"

        maker = ProgressMessageMaker(1)
        assert maker.logger_name == "unittest.case"

    it "uses make_info":
        a = mock.Mock(name="a")
        body = mock.Mock(name="body")
        message = mock.Mock(name="message")

        info = mock.Mock(name="info")
        do_log = mock.Mock(name="do_log")
        make_info = mock.Mock(name="make_info", return_value=info)

        maker = ProgressMessageMaker()
        with mock.patch.multiple(maker, make_info=make_info, do_log=do_log):
            assert maker(body, message, do_log=False, a=a) is info

        make_info.assert_called_once_with(body, message, a=a)
        assert len(do_log.mock_calls) == 0

    it "uses do_log if we ask it to":
        a = mock.Mock(name="a")
        body = mock.Mock(name="body")
        message = mock.Mock(name="message")

        info = mock.Mock(name="info")
        do_log = mock.Mock(name="do_log")
        make_info = mock.Mock(name="make_info", return_value=info)

        maker = ProgressMessageMaker()
        with mock.patch.multiple(maker, make_info=make_info, do_log=do_log):
            assert maker(body, message, do_log=True, a=a) is info

        make_info.assert_called_once_with(body, message, a=a)
        do_log.assert_called_once_with(body, message, info, a=a)

    describe "make_info":
        it "converts normal exceptions":
            a = mock.Mock(name="a")
            error = ValueError("NOPE")
            body = mock.Mock(name="body")
            info = ProgressMessageMaker().make_info(body, error, a=a)
            assert info == {"error_code": "ValueError", "error": "NOPE", "a": a}

        it "converts exceptions with an as_dict":
            b = mock.Mock(name="b")

            class BadThings(Exception):
                def as_dict(self):
                    return {"one": 1}

            error = BadThings()

            body = mock.Mock(name="body")
            info = ProgressMessageMaker().make_info(body, error, b=b)
            assert info == {"error_code": "BadThings", "error": {"one": 1}, "b": b}

        it "converts message of None to done True":
            c = mock.Mock(name="c")
            body = mock.Mock(name="body")
            info = ProgressMessageMaker().make_info(body, None, c=c)
            assert info == {"done": True, "c": c}

        it "passes dictionary through as is and with kwargs":
            d = mock.Mock(name="d")
            body = mock.Mock(name="body")
            message = {"one": "two"}
            info = ProgressMessageMaker().make_info(body, message)
            assert info == {"one": "two"}

            info = ProgressMessageMaker().make_info(body, message, d=d)
            assert info == {"one": "two", "d": d}

            # and doesn't modify the original
            assert message == {"one": "two"}

        it "pass through message as info otherwise":
            d = mock.Mock(name="d")
            body = mock.Mock(name="body")
            message = mock.Mock(name="message")
            info = ProgressMessageMaker().make_info(body, message, d=d)
            assert info == {"info": message, "d": d}
