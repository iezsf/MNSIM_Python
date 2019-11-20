#!/usr/bin/python
# -*-coding:utf-8-*-
import torch
import sys
import os
import math
import configparser as cp
work_path = os.path.dirname(os.getcwd())
sys.path.append(work_path)
from MNSIM.Hardware_Model import *
from MNSIM.Hardware_Model.Crossbar import crossbar
from MNSIM.Hardware_Model.PE import ProcessElement
from MNSIM.Hardware_Model.Buffer import buffer
from MNSIM.Hardware_Model.Bank import bank
from MNSIM.Interface.interface import *
from MNSIM.Mapping_Model.Bank_connection_graph import BCG
from MNSIM.Latency_Model.Bank_latency import bank_latency_analysis
from MNSIM.Latency_Model.Pooling_latency import pooling_latency_analysis
import collections

class Model_latency():
    def __init__(self, NetStruct, SimConfig_path):
        modelL_config = cp.ConfigParser()
        modelL_config.read(SimConfig_path, encoding='UTF-8')
        self.inter_bank_bandwidth = float(modelL_config.get('Bank level', 'Inter_Bank_Bandwidth'))
        self.graph = BCG(NetStruct, SimConfig_path)
        self.graph.mapping_net()
        self.graph.calculate_transfer_distance()
        self.begin_time = []
        self.finish_time = []
        self.layer_bank_latency = []
        self.NetStruct = NetStruct
        self.SimConfig_path = SimConfig_path
        self.uni_begin_time = []
        self.uni_finish_time = []
        self.occupancy = []
    def caculate_model_latency_1(self):
        for layer_id in range(len(self.NetStruct)):
            layer_dict = self.NetStruct[layer_id][0][0]
            if layer_id == 0:
                # for the first layer, first layer must be conv layer
                self.begin_time.append([])
                self.finish_time.append([])
                self.uni_begin_time.append([])
                self.uni_finish_time.append([])
                output_size = list(map(int, layer_dict['Outputsize']))
                input_size = list(map(int, layer_dict['Inputsize']))
                kernelsize = int(layer_dict['Kernelsize'])
                stride = int(layer_dict['Stride'])
                inputchannel = int(layer_dict['Inputchannel'])
                outputchannel = int(layer_dict['Outputchannel'])
                padding = int(layer_dict['Padding'])
                inputbit = int(layer_dict['Inputbit'])
                outputbit = int(layer_dict['outputbit'])
                # print(self.graph.layer_bankinfo[layer_id]['max_row'])
                input_channel_PE = self.graph.layer_bankinfo[layer_id]['max_row']/(kernelsize**2)
                 # the input channel number each PE processes
                temp_bank_latency = bank_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                          read_row=self.graph.layer_bankinfo[layer_id]['max_row'],
                                                          read_column=self.graph.layer_bankinfo[layer_id]['max_column'],
                                                          indata=0, rdata=0, inprecision=inputbit,
                                                          PE_num=self.graph.layer_bankinfo[layer_id]['max_PE']
                                                          )
                merge_time = self.graph.inLayer_distance[0][layer_id] * (temp_bank_latency.digital_period +
                                                                         self.graph.layer_bankinfo[layer_id][
                                                                             'max_column'] * outputbit / self.inter_bank_bandwidth)
                    # Todo: update merge time (adder tree) and transfer data volume
                transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            outputchannel * outputbit / self.inter_bank_bandwidth)
                    # Todo: update transfer data volume
                for i in range(output_size[0]):
                    for j in range(output_size[1]):
                        if (i==0) & (j==0):
                            # the first output
                            indata = (input_channel_PE*output_size[1]*max(kernelsize-padding-1,0)+max(kernelsize-padding,0))*inputbit/8
                                # fill the line buffer
                            rdata = self.graph.layer_bankinfo[layer_id]['max_row']*inputbit/8
                                # from the line buffer to the input reg
                            temp_bank_latency.update_bank_latency(indata=indata,rdata=rdata)
                            compute_time = temp_bank_latency.bank_latency + merge_time + transfer_time
                            self.begin_time[0].append(0)
                            self.finish_time[0].append(compute_time)
                            self.uni_begin_time[0].append(0)
                            self.uni_finish_time[0].append(compute_time)
                            # print(self.finish_time[0])
                        elif j==0:
                            indata = input_channel_PE*stride*max(kernelsize-padding,0)*inputbit/8
                                # line feed in line buffer
                            rdata = self.graph.layer_bankinfo[layer_id]['max_row']*inputbit/8
                                # from the line buffer to the input reg
                            temp_bank_latency.update_bank_latency(indata=indata,rdata=rdata)
                            begin_time = self.finish_time[0][(i-1)*output_size[1]+output_size[1]-1]
                            compute_time = temp_bank_latency.bank_latency + merge_time + transfer_time +\
                                           begin_time
                            if begin_time not in self.begin_time[0]:
                                self.uni_begin_time[0].append(begin_time)
                                self.uni_finish_time[0].append(compute_time)
                            else:
                                self.uni_finish_time[0][self.begin_time[0].index(begin_time)] = max(compute_time,
                                                        self.uni_finish_time[0][self.begin_time[0].index(begin_time)])
                            self.begin_time[0].append(begin_time)
                            self.finish_time[0].append(compute_time)
                            # print(self.finish_time[0])
                        else:
                            indata = input_channel_PE*stride**2*inputbit/8
                                # write new input data to line buffer
                            rdata = stride*kernelsize*input_channel_PE*inputbit/8
                            temp_bank_latency.update_bank_latency(indata=indata,rdata=rdata)
                            begin_time = self.finish_time[0][i * output_size[1] + j - 1]
                            compute_time = temp_bank_latency.bank_latency + merge_time + transfer_time + \
                                           begin_time
                            if begin_time not in self.begin_time[0]:
                                self.uni_begin_time[0].append(begin_time)
                                self.uni_finish_time[0].append(compute_time)
                            else:
                                self.uni_finish_time[0][self.begin_time[0].index(begin_time)] = max(compute_time,
                                                        self.uni_finish_time[0][self.begin_time[0].index(begin_time)])
                            self.begin_time[0].append(begin_time)
                            self.finish_time[0].append(compute_time)
                # print("start time: ", self.begin_time[0])
                # print("finish time:", self.finish_time[0])
                # print('==============================')
            else:
                if layer_dict['type'] == 'conv':
                    self.begin_time.append([])
                    self.finish_time.append([])
                    self.uni_begin_time.append([])
                    self.uni_finish_time.append([])
                    output_size = list(map(int, layer_dict['Outputsize']))
                    input_size = list(map(int, layer_dict['Inputsize']))
                    kernelsize = int(layer_dict['Kernelsize'])
                    stride = int(layer_dict['Stride'])
                    inputchannel = int(layer_dict['Inputchannel'])
                    outputchannel = int(layer_dict['Outputchannel'])
                    padding = int(layer_dict['Padding'])
                    inputbit = int(layer_dict['Inputbit'])
                    outputbit = int(layer_dict['outputbit'])
                    # print(self.graph.layer_bankinfo[layer_id]['max_row'])
                    input_channel_PE = self.graph.layer_bankinfo[layer_id]['max_row'] / (kernelsize ** 2)
                    # the input channel number each PE processes
                    temp_bank_latency = bank_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                              read_row=self.graph.layer_bankinfo[layer_id]['max_row'],
                                                              read_column=self.graph.layer_bankinfo[layer_id]['max_column'],
                                                              indata=0, rdata=0, inprecision=inputbit,
                                                              PE_num=self.graph.layer_bankinfo[layer_id]['max_PE']
                                                              )
                    merge_time = self.graph.inLayer_distance[0][layer_id] * (temp_bank_latency.digital_period +
                                                                             self.graph.layer_bankinfo[layer_id]['max_column'] *
                                                                             outputbit / self.inter_bank_bandwidth)
                    # Todo: update merge time (adder tree) and transfer data volume
                    transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            outputchannel * outputbit / self.inter_bank_bandwidth)
                    # Todo: update transfer data volume
                    for i in range(output_size[0]):
                        for j in range(output_size[1]):
                            last_layer_pos = min((kernelsize + stride * i - padding - 1) * input_size[1] + \
                                             kernelsize + stride * j - padding - 1, len(self.finish_time[layer_id-1])-1)
                            if last_layer_pos > len(self.finish_time[layer_id-1])-1:
                                print("pos error", i,j)
                            if (i == 0) & (j == 0):
                                # the first output
                                indata = input_channel_PE * output_size[1] * max(kernelsize - padding - 1, 0) + max(
                                    kernelsize - padding, 0)*inputbit/8
                                # fill the line buffer
                                rdata = self.graph.layer_bankinfo[layer_id]['max_row']*inputbit/8
                                # from the line buffer to the input reg
                                temp_bank_latency.update_bank_latency(indata=indata, rdata=rdata)
                                begin_time = self.finish_time[layer_id-1][last_layer_pos]
                                compute_time = temp_bank_latency.bank_latency + merge_time + transfer_time + \
                                               begin_time
                                # consider the input data generation time
                                if begin_time not in self.begin_time[layer_id]:
                                    self.uni_begin_time[layer_id].append(begin_time)
                                    self.uni_finish_time[layer_id].append(compute_time)
                                else:
                                    self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)] =\
                                        max(compute_time,self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)])
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                # print(self.finish_time[layer_id])
                            elif j == 0:
                                indata = input_channel_PE * stride * max(kernelsize - padding, 0)*inputbit/8
                                # line feed in line buffer
                                rdata = self.graph.layer_bankinfo[layer_id]['max_row']*inputbit/8
                                # from the line buffer to the input reg
                                temp_bank_latency.update_bank_latency(indata=indata, rdata=rdata)
                                begin_time = max(self.finish_time[layer_id-1][last_layer_pos],
                                                   self.finish_time[layer_id][(i - 1) * output_size[1] + output_size[1] - 1])
                                # max (the required input data generation time, previous point computation complete time)
                                compute_time = temp_bank_latency.bank_latency + merge_time + transfer_time + \
                                               begin_time
                                if begin_time not in self.begin_time[layer_id]:
                                    self.uni_begin_time[layer_id].append(begin_time)
                                    self.uni_finish_time[layer_id].append(compute_time)
                                else:
                                    self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)] =\
                                        max(compute_time,self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)])
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                # print(self.finish_time[layer_id])
                            else:
                                indata = input_channel_PE * stride ** 2*inputbit/8
                                # write new input data to line buffer
                                rdata = stride * kernelsize * input_channel_PE*inputbit/8
                                temp_bank_latency.update_bank_latency(indata=indata, rdata=rdata)
                                begin_time = max(self.finish_time[layer_id-1][last_layer_pos],
                                                   self.finish_time[layer_id][i * output_size[1] + j - 1])
                                # max (the required input data generation time, previous point computation complete time)
                                compute_time = temp_bank_latency.bank_latency + merge_time + transfer_time + \
                                               begin_time
                                if begin_time not in self.begin_time[layer_id]:
                                    self.uni_begin_time[layer_id].append(begin_time)
                                    self.uni_finish_time[layer_id].append(compute_time)
                                else:
                                    self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)] =\
                                        max(compute_time,self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)])
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                    # print("start time: ",self.begin_time[layer_id])
                    # print("finish time:",self.finish_time[layer_id])
                    # print('==============================')
                elif layer_dict['type'] == 'fc':
                    output_size = int(layer_dict['Outfeature'])
                    input_size = int(layer_dict['Infeature'])
                    inputbit = int(layer_dict['Inputbit'])
                    outputbit = int(layer_dict['outputbit'])
                    self.begin_time.append([])
                    self.finish_time.append([])
                    self.uni_begin_time.append([])
                    self.uni_finish_time.append([])
                    indata = self.graph.layer_bankinfo[layer_id]['max_row']*inputbit/8
                    rdata = indata*inputbit/8
                    temp_bank_latency = bank_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                              read_row=self.graph.layer_bankinfo[layer_id]['max_row'],
                                                              read_column=self.graph.layer_bankinfo[layer_id]['max_column'],
                                                              indata=indata, rdata=rdata, inprecision=inputbit,
                                                              PE_num=self.graph.layer_bankinfo[layer_id]['max_PE']
                                                              )
                    merge_time = self.graph.inLayer_distance[0][layer_id] * (temp_bank_latency.digital_period +
                                                                             self.graph.layer_bankinfo[layer_id]['max_column'] *
                                                                             outputbit / self.inter_bank_bandwidth)
                    # Todo: update merge time (adder tree) and transfer data volume
                    transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            output_size * outputbit / self.inter_bank_bandwidth)
                    begin_time = self.finish_time[layer_id-1][-1]
                    compute_time = temp_bank_latency.bank_latency + merge_time + transfer_time + begin_time
                    if begin_time not in self.begin_time[layer_id]:
                        self.uni_begin_time[layer_id].append(begin_time)
                        self.uni_finish_time[layer_id].append(compute_time)
                    else:
                        self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)] = \
                            max(compute_time, self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)])
                    self.begin_time[layer_id] = output_size * [begin_time]
                    self.finish_time[layer_id]= output_size*[compute_time]
                    # print("start time: ",self.begin_time[layer_id])
                    # print("finish time:",self.finish_time[layer_id])
                    # print('==============================')
                else:
                    assert layer_dict['type'] == 'pooling', "Layer type can only be conv/fc/pooling"
                    self.begin_time.append([])
                    self.finish_time.append([])
                    self.uni_begin_time.append([])
                    self.uni_finish_time.append([])
                    output_size = list(map(int, layer_dict['Outputsize']))
                    input_size = list(map(int, layer_dict['Inputsize']))
                    kernelsize = int(layer_dict['Kernelsize'])
                    stride = int(layer_dict['Stride'])
                    inputchannel = int(layer_dict['Inputchannel'])
                    outputchannel = int(layer_dict['Outputchannel'])
                    padding = int(layer_dict['Padding'])
                    inputbit = int(layer_dict['Inputbit'])
                    outputbit = int(layer_dict['outputbit'])
                    temp_pooling_latency = pooling_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                                    indata=0, rdata=0)
                    merge_time = 0
                    # Todo: update merge time of pooling bank
                    transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            outputchannel * outputbit / self.inter_bank_bandwidth)
                    # Todo: update transfer data volume
                    for i in range(output_size[0]):
                        for j in range(output_size[1]):
                            last_layer_pos = min((kernelsize + stride * i - padding - 1) * input_size[1] + \
                                                 kernelsize + stride * j - padding - 1,
                                                 len(self.finish_time[layer_id - 1]) - 1)
                            if (i == 0) & (j == 0):
                                # the first output
                                indata = inputchannel * output_size[1] * max(kernelsize - padding - 1, 0) + max(
                                    kernelsize - padding, 0)*inputbit/8
                                # fill the line buffer
                                rdata = inputchannel*kernelsize**2*inputbit/8
                                # from the line buffer to the input reg
                                temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)
                                begin_time = self.finish_time[layer_id - 1][last_layer_pos]
                                compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + \
                                               begin_time
                                # consider the input data generation time
                                if begin_time not in self.begin_time[layer_id]:
                                    self.uni_begin_time[layer_id].append(begin_time)
                                    self.uni_finish_time[layer_id].append(compute_time)
                                else:
                                    self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)] =\
                                        max(compute_time,self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)])
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                # print(self.finish_time[layer_id])
                            elif j == 0:
                                indata = inputchannel * stride * max(kernelsize - padding, 0)*inputbit/8
                                # line feed in line buffer
                                rdata = inputchannel*kernelsize**2*inputbit/8
                                # from the line buffer to the input reg
                                temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)
                                begin_time = max(self.finish_time[layer_id - 1][last_layer_pos],
                                                   self.finish_time[layer_id][(i - 1) * output_size[1] + output_size[1] - 1])
                                compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + \
                                               begin_time
                                if begin_time not in self.begin_time[layer_id]:
                                    self.uni_begin_time[layer_id].append(begin_time)
                                    self.uni_finish_time[layer_id].append(compute_time)
                                else:
                                    self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)] =\
                                        max(compute_time,self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)])
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                # print(self.finish_time[layer_id])
                            else:
                                indata = inputchannel * stride ** 2*inputbit/8
                                # write new input data to line buffer
                                rdata = stride * kernelsize * inputchannel*inputbit/8
                                temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)
                                begin_time = max(self.finish_time[layer_id - 1][last_layer_pos],
                                                   self.finish_time[layer_id][i * output_size[1] + j - 1])
                                compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + \
                                               begin_time
                                if begin_time not in self.begin_time[layer_id]:
                                    self.uni_begin_time[layer_id].append(begin_time)
                                    self.uni_finish_time[layer_id].append(compute_time)
                                else:
                                    self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)] =\
                                        max(compute_time,self.uni_finish_time[layer_id][self.begin_time[layer_id].index(begin_time)])
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                    # print("start time: ",self.begin_time[layer_id])
                    # print("finish time:",self.finish_time[layer_id])
                    # print('==============================')
            temp_runtime = list(map(lambda x: x[0]-x[1], zip(self.uni_finish_time[layer_id], self.uni_begin_time[layer_id])))
            self.occupancy.append(sum(temp_runtime)/(max(self.uni_finish_time[layer_id])-min(self.uni_begin_time[layer_id])))


if __name__ == '__main__':
    test_SimConfig_path = os.path.join(os.path.dirname(os.path.dirname(os.getcwd())), "SimConfig.ini")
    test_weights_file_path = os.path.join(os.path.dirname(os.path.dirname(os.getcwd())),
                                          "cifar10_vgg8_params.pth")

    __TestInterface = TrainTestInterface('vgg8', 'MNSIM.Interface.cifar10', test_SimConfig_path, test_weights_file_path,
                                         'cpu')
    structure_file = __TestInterface.get_structure()

    test = Model_latency(structure_file, test_SimConfig_path)
    test.caculate_model_latency_1()
    for i in range(len(test.begin_time)):
        print("start time: ", test.begin_time[i])
        print("finish time:",test.finish_time[i])
        print("used time:", list(map(lambda x: x[0]-x[1], zip(test.uni_finish_time[i], test.uni_begin_time[i]))))
        print("Occupancy:", test.occupancy[i])
        print('==============================')
    print("Latency simulation finished!")