"""Reproduce the 229-byte matcher; optional development dependency: onnx."""
from pathlib import Path
import onnx
from onnx import helper,TensorProto

graph=helper.make_graph([
    helper.make_node('Transpose',['references'],['reference_t'],perm=[1,0]),
    helper.make_node('MatMul',['patches','reference_t'],['scores'])],
    'cosine_similarity',[
        helper.make_tensor_value_info('patches',TensorProto.FLOAT,['n','d']),
        helper.make_tensor_value_info('references',TensorProto.FLOAT,['m','d'])],
    [helper.make_tensor_value_info('scores',TensorProto.FLOAT,['n','m'])])
model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)],producer_name='bulldog-xiangqi');model.ir_version=8
onnx.checker.check_model(model)
onnx.save(model,Path(__file__).resolve().parents[1]/'connector/bridge/appearance.onnx')
