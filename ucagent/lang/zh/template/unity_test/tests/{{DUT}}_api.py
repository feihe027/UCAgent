#coding=utf-8

import pytest
import ucagent
from {{DUT}}_function_coverage_def import get_coverage_groups
from toffee_test.reporter import set_func_coverage, set_line_coverage, get_file_in_tmp_dir
from toffee_test.reporter import set_user_info, set_title_info
from toffee import Bundle, Signals, Signal

# import your dut module here
from {{DUT}} import DUT{{DUT}}  # Replace with the actual DUT class import

import os


def current_path_file(file_name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name)


def get_test_artifact_name(request, default_name):
    if request is None:
        return default_name

    node = request.node
    tc_name = node.name
    node_path = getattr(node, "path", None) or getattr(node, "fspath", None)
    if node_path is not None:
        tc_name = f"{os.path.splitext(os.path.basename(str(node_path)))[0]}__{tc_name}"

    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tc_name)


def get_test_waveform_artifact_name(request, default_name):
    if request is None:
        return default_name

    node = request.node
    node_path = getattr(node, "path", None) or getattr(node, "fspath", None)
    if node_path is not None:
        file_name = os.path.splitext(os.path.basename(str(node_path)))[0]
        tc_name = f"{file_name}-{node.name}"
    else:
        tc_name = node.name

    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tc_name)


def get_coverage_data_path(request, new_path:bool):
    # 通过toffee_test.reporter提供的get_file_in_tmp_dir方法可以让各用例产生的文件名称不重复 (获取新路径需要new_path=True，获取已有路径new_path=False)
    # 获取测试用例名称，为每个测试用例创建对应的代码行覆盖率文件
    tc_name = get_test_artifact_name(request, "{{DUT}}")
    return get_file_in_tmp_dir(request, current_path_file("data/"), f"{tc_name}.dat",  new_path=new_path)


def get_waveform_path(request, new_path:bool, suffix="fst"):
    # 通过toffee_test.reporter提供的get_file_in_tmp_dir方法可以让各用例产生的文件名称不重复 (获取新路径需要new_path=True，获取已有路径new_path=False)
    # 获取测试文件名称和测试函数名称，为每个测试函数创建对应的波形
    tc_name = get_test_waveform_artifact_name(request, "{{DUT}}")
    suffix = (suffix or "fst").lstrip(".")
    return get_file_in_tmp_dir(request, current_path_file("data/"), f"{tc_name}.{suffix}",  new_path=new_path)


def get_new_waveform_path(request, suffix="fst"):
    waveform_path = get_waveform_path(request, new_path=True, suffix=suffix)
    if os.path.exists(waveform_path):
        os.remove(waveform_path)
    return waveform_path


def configure_waveform_for_test_case(dut, request, waveform_path):
    # pytest 下部分 DUT wrapper 会复用同一个仿真 runtime，构造函数的 waveform_filename
    # 只在首次实例化时生效；这里显式按测试函数切换波形，保证每个测试函数一个波形文件。
    waveform_key = get_test_waveform_artifact_name(request, "{{DUT}}")
    current_key = getattr(dut, "_ucagent_waveform_key", None)
    current_path = getattr(dut, "_ucagent_waveform_path", None)

    if current_key == waveform_key and current_path == waveform_path:
        return

    if current_key is not None and hasattr(dut, "FlushWaveform"):
        dut.FlushWaveform()

    dut.SetWaveform(waveform_path)
    setattr(dut, "_ucagent_waveform_key", waveform_key)
    setattr(dut, "_ucagent_waveform_path", waveform_path)


def create_dut(request):
    """
    Create a new instance of the {{DUT}} for testing.
    
    Returns:
        dut_instance: An instance of the {{DUT}} class.
    """
    # 如果是正在生成测试模板，返回fake DUT用于提速（模板中不会真运行DUT）
    if ucagent.is_imp_test_template():
        return ucagent.get_fake_dut(DUT{{DUT}})

    # Replace with the actual instantiation and initialization of your DUT
    dut = DUT{{DUT}}()

    # 设置覆盖率生成文件(必须设置覆盖率文件，否则无法统计覆盖率，导致测试失败)
    dut.SetCoverage(get_coverage_data_path(request, new_path=True))

    # 设置波形生成文件；每个测试函数使用独立且未被占用的波形路径，避免波形后端自动追加 _r0 后缀
    configure_waveform_for_test_case(
        dut,
        request,
        get_new_waveform_path(request, suffix=dut.GetWaveFormat()),
    )

    return dut


@pytest.fixture(scope="function") # 用scope="function"确保每个测试函数创建独立DUT和波形文件
def dut(request):
    dut = create_dut(request)                         # 创建DUT
    func_coverage_group = get_coverage_groups(dut)
    # 请在这里根据DUT是否为时序电路判断是否需要调用 dut.InitClock
    # dut.InitClock("clk")

    # 上升沿采样，StepRis也适用于组合电路用dut.Step推进时采样.
    # 必须要有g.sample()采样覆盖组, 如何不在StepRis/StepFal中采样，则需要在test function中手动调用，否则无法统计覆盖率导致失败
    dut.StepRis(lambda _: [g.sample()
                           for g in
                           func_coverage_group])

    # 以属性名称fc_cover保存覆盖组到DUT
    setattr(dut, "fc_cover",
            {g.name:g for g in func_coverage_group})

    # 返回DUT实例
    yield dut

    # 测试后处理
    # 需要在测试结束的时候，通过set_func_coverage把覆盖组传递给toffee_test*
    set_func_coverage(request, func_coverage_group)

    # 设置需要收集的代码行覆盖率文件(获取已有路径new_path=False) 向toffee_test传代码行递覆盖率数据
    # 代码行覆盖率 ignore 文件的固定路径为当前文件所在目录下的：{{DUT}}.ignore，请不要改变
    set_line_coverage(request, get_coverage_data_path(request, new_path=False), ignore=current_path_file("{{DUT}}.ignore"))

    # 设置用户信息到报告
    set_user_info("UCAgent-{{Version}}", "{{Email}}")
    set_title_info("{{DUT}} Test Report")

    for g in func_coverage_group:                        # 采样覆盖组
        g.clear()                                        # 清空统计
    dut.Finish()                                         # 清理DUT，每个DUT class 都有 Finish 方法

@pytest.fixture(scope="function") # 用scope="function"确保每个测试用例都创建了一个全新的 Mock DUT
def mock_dut():
    return ucagent.get_mock_dut_from(DUT{{DUT}})

# 根据需要定义子Bundle
# class MyPort(Bundle):
#     # 定义引脚多个引脚用Signals
#     signal1, signal2 = Signals(2)
#     # 定义单个引脚用Signal
#     signal3 = Signal()
#     # 根据需要定义Port对应的操作
#     def some_operation(self):
#         ...


# 定义{{DUT}}Env类，封装DUT的引脚和常用操作
class {{DUT}}Env:
    '''请在这里对Env的功能进行描述'''

    def __init__(self, dut):
        self.dut = dut
        # 请在这里根据DUT的引脚定义，提供toffee.Bundle进行引脚封装
        #  1.如果引脚有多组，且有不同前缀，请用from_prefix方法
        # self.some_input1 = MyPort.from_prefix("some_input_") # 去掉前缀后的dut引脚必须和MyPort中的引脚成员同名，例如some_input_signal1和signal1对应
        # self.some_input1.bind(dut)
        #  2.如果引脚无法分组，请用from_dict方法进行映射
        # self.some_input2 = MyPort.from_dict({...})
        # self.some_input2.bind(dut)
        # 根据需要添加StepRis回调:
        # self.dut.StepRis(self.handle_axi_transactions)

        # 在最后通过 Bundle 的 set_all(0) 方法, 把所有输入引脚赋值为0
        # self.some_input1.set_all(0)
        # self.some_input2.set_all(0)

    # 根据需要添加清空Env注册的回调函数
    # def clear_cbs(self):
    #     self.dut.xclock.RemoveStepRisCbByDesc(self.handle_axi_transactions.__name__)
    #     ...

    # 根据需要定义Env的常用操作
    #def reset(self):
    #    # 根据DUT的复位方式，完成复位操作
    #    ...

    # 直接导出DUT的通用操作Step
    def Step(self, i:int = 1):
        return self.dut.Step(i)


# 定义env fixture, 请取消下面的注释，并根据需要修改名称
@pytest.fixture(scope="function") # 用scope="function"确保每个测试用例都创建了一个全新的Env
def env(dut):
    # 一般情况下为每个test都创建全新的 env 不需要 yield
    return {{DUT}}Env(dut)


# 定义其他Env
# @pytest.fixture(scope="function") # 用scope="function"确保每个测试用例都创建了一个全新的Env
# def env1(dut):
#     return MyEnv1(dut)
#
#
# 根据DUT的功能需要，定义API函数， API函数需要通用且稳定，不是越多越好
# def api_{{DUT}}_{operation_name}(env, ...):
#    """
#    api description and parameters
#    ...
#    """
#    env.some_input.value = value
#    env.Step()
#    return env.some_output.value
#    # Replace with the actual API function for your DUT
#    ...


# 本文件为模板，请根据需要修改，删除不需要的代码和注释
