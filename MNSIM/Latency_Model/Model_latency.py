#!/usr/bin/python
# -*-coding:utf-8-*-
import sys
import os
import configparser as cp
work_path = os.path.dirname(os.getcwd())
sys.path.append(work_path)
import numpy as np
from MNSIM.Interface.interface import *
from MNSIM.Mapping_Model.Tile_connection_graph import TCG
from MNSIM.Latency_Model.Tile_latency import tile_latency_analysis
from MNSIM.Latency_Model.Pooling_latency import pooling_latency_analysis

def merge_interval(interval):
    if len(interval) == 0:
        return []
    result = []
    interval.sort()
    lower_bound = interval[0][0]
    upper_bound = interval[0][1]
    for index in range(1,len(interval)):
        if interval[index][0] > upper_bound:
            result.append([lower_bound,upper_bound])
            lower_bound = interval[index][0]
            upper_bound = interval[index][1]
        else:
            if interval[index][1] > upper_bound:
                upper_bound = interval[index][1]
    result.append([lower_bound, upper_bound])
    return result

def Search(value, data):
    pos = 0
    if value > data[-1]:
        return len(data)
    while(value > data[pos]):
        pos += 1
    return pos


def Split_map(padding, outputsize, multiple): # 对下一层进行划分
    base = outputsize // multiple
    res = outputsize - base * multiple
    split = [] # split the outputsize
    for i in range(multiple):
        if i < res:
            split.append(base + 1)
        else:
            split.append(base)
    return split


class Model_latency():
    def __init__(self, NetStruct, SimConfig_path, multiple=None):
        modelL_config = cp.ConfigParser()
        modelL_config.read(SimConfig_path, encoding='UTF-8')
        self.inter_tile_bandwidth = float(modelL_config.get('Tile level', 'Inter_Tile_Bandwidth'))
        self.NetStruct = NetStruct
        if multiple is None:
            multiple = [1] * len(self.NetStruct)
        self.graph = TCG(NetStruct, SimConfig_path, multiple)
        self.graph.mapping_net()
        self.graph.calculate_transfer_distance()
        self.begin_time = []
        self.finish_time = []
        self.layer_tile_latency = []

        self.SimConfig_path = SimConfig_path
        self.compute_interval = []
        self.occupancy = []
        self.multiple = multiple

        self.buffer_latency = []
        self.computing_latency = []
        self.DAC_latency = []
        self.xbar_latency = []
        self.ADC_latency = []
        self.digital_latency = []
        self.intra_tile_latency = []
        self.inter_tile_latency = []
        self.tile_merge_latency = []
        self.tile_transfer_latency = []

        self.total_buffer_latency = []
        self.total_computing_latency = []
        self.total_DAC_latency = []
        self.total_xbar_latency = []
        self.total_ADC_latency = []
        self.total_digital_latency = []
        self.total_intra_tile_latency = []
        self.total_inter_tile_latency = []
        self.total_tile_merge_latency = []
        self.total_tile_transfer_latency = []

        self.layer_type = []
        self.layer_split = []
        self.pre_max_time = 0

    def Judge(self, last_layer_pos, current_layer_id):
        layer_dict = self.NetStruct[current_layer_id][0][0]
        # print(current_layer_id)
        if layer_dict['type'] is not 'pooling':
            assert layer_dict['type'] == 'conv', "fc no need to be judged"
        kernelsize = int(layer_dict['Kernelsize'])
        last_split = self.layer_split[current_layer_id-1]
        input_size = list(map(int, layer_dict['Inputsize']))[1]
        Row = last_layer_pos // input_size
        last_column = last_layer_pos % input_size  # begin from 0
        m = 0
        pos = 0
        while last_column > last_split[m]:
            last_column -= last_split[m]
            m += 1
        if last_column - kernelsize >= 0:
            return last_layer_pos
        else:
            for i in range(m):
               pos += last_split[m]  # 得到每个分块的最后一个点
            return pos-1*(m != 0) + Row * input_size

    def calculate_model_latency_nopipe(self):
        for layer_id in range(len(self.NetStruct)):
            layer_dict = self.NetStruct[layer_id][0][0]
            if layer_id == 0:
                # for the first layer, first layer must be conv layer
                self.begin_time.append([])
                self.finish_time.append([])
                self.compute_interval.append([])

                self.buffer_latency.append([])
                self.computing_latency.append([])
                self.DAC_latency.append([])
                self.xbar_latency.append([])
                self.ADC_latency.append([])
                self.digital_latency.append([])
                self.intra_tile_latency.append([])
                self.inter_tile_latency.append([])
                self.tile_merge_latency.append([])
                self.tile_transfer_latency.append([])
                output_size = list(map(int, layer_dict['Outputsize']))
                input_size = list(map(int, layer_dict['Inputsize']))
                kernelsize = int(layer_dict['Kernelsize'])
                stride = int(layer_dict['Stride'])
                inputchannel = int(layer_dict['Inputchannel'])
                outputchannel = int(layer_dict['Outputchannel'])
                padding = int(layer_dict['Padding'])
                inputbit = int(layer_dict['Inputbit'])
                outputbit = int(layer_dict['outputbit'])
                # print(self.graph.layer_tileinfo[layer_id]['max_row'])
                input_channel_PE = self.graph.layer_tileinfo[layer_id]['max_row'] / (kernelsize ** 2)
                 # the input channel number each PE processes
                temp_tile_latency = tile_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                          read_row=self.graph.layer_tileinfo[layer_id]['max_row'],
                                                          read_column=self.graph.layer_tileinfo[layer_id]['max_column'],
                                                          indata=0, rdata=0, inprecision=inputbit,
                                                          PE_num=self.graph.layer_tileinfo[layer_id]['max_PE']
                                                          )
                # merge_time = self.graph.inLayer_distance[0][layer_id] * (temp_tile_latency.digital_period +
                #                                                          self.graph.layer_tileinfo[layer_id][
                #                                                              'max_column'] * outputbit / self.inter_tile_bandwidth)
                merge_time = (self.graph.layer_tileinfo[layer_id]['tilenum'] - 1) * temp_tile_latency.digital_period + \
                             self.graph.inLayer_distance[0][layer_id] * self.graph.layer_tileinfo[layer_id]['max_column'] * \
                             outputbit / self.inter_tile_bandwidth

                    # Todo: update merge time (adder tree) and transfer data volume
                transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            outputchannel * outputbit / self.inter_tile_bandwidth)
                    # Todo: update transfer data volume
                for i in range(output_size[0]):
                    for j in range(output_size[1]):
                        if (i==0) & (j==0):
                            # the first output
                            indata = input_channel_PE*(input_size[1]*max(kernelsize-padding-1,0)+max(kernelsize-padding,0))*inputbit/8
                                # fill the line buffer
                            rdata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                                # from the line buffer to the input reg
                            temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                            compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time
                            self.begin_time[0].append(0)
                            self.finish_time[0].append(compute_time)
                            self.compute_interval[0].append([0,compute_time])

                            self.buffer_latency[layer_id].append(temp_tile_latency.buf_wlatency+temp_tile_latency.buf_rlatency)
                            self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                            self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                            self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                            self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                            self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency+
                                                                  temp_tile_latency.ireg_latency+temp_tile_latency.shiftadd_latency+
                                                                  temp_tile_latency.oreg_latency+temp_tile_latency.merge_latency)
                            self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                            self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                            self.tile_merge_latency[layer_id].append(merge_time)
                            self.tile_transfer_latency[layer_id].append(transfer_time)
                            # print(self.finish_time[0])
                        elif j==0:
                            indata = input_channel_PE*stride*max(kernelsize-padding,0)*inputbit/8
                                # line feed in line buffer
                            rdata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                                # from the line buffer to the input reg
                            temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                            begin_time = self.finish_time[0][(i-1)*output_size[1]+output_size[1]-1]
                            compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + \
                                           begin_time
                            self.begin_time[0].append(begin_time)
                            self.finish_time[0].append(compute_time)
                            self.compute_interval[0].append([begin_time,compute_time])

                            self.buffer_latency[layer_id].append(
                                temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                            self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                            self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                            self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                            self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                            self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                  temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                  temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                            self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                            self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                            self.tile_merge_latency[layer_id].append(merge_time)
                            self.tile_transfer_latency[layer_id].append(transfer_time)
                            # print(self.finish_time[0])
                        else:
                            indata = input_channel_PE*stride**2*inputbit/8
                                # write new input data to line buffer
                            rdata = stride*kernelsize*input_channel_PE*inputbit/8
                            temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                            begin_time = self.finish_time[0][i * output_size[1] + j - 1]
                            compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + \
                                           begin_time
                            self.begin_time[0].append(begin_time)
                            self.finish_time[0].append(compute_time)
                            self.compute_interval[0].append([begin_time,compute_time])

                            self.buffer_latency[layer_id].append(
                                temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                            self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                            self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                            self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                            self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                            self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                  temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                  temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                            self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                            self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                            self.tile_merge_latency[layer_id].append(merge_time)
                            self.tile_transfer_latency[layer_id].append(transfer_time)
                # print("start time: ", self.begin_time[0])
                # print("finish time:", self.finish_time[0])
                # print('==============================')
            else:
                if layer_dict['type'] == 'conv':
                    self.begin_time.append([])
                    self.finish_time.append([])
                    self.compute_interval.append([])

                    self.buffer_latency.append([])
                    self.computing_latency.append([])
                    self.DAC_latency.append([])
                    self.xbar_latency.append([])
                    self.ADC_latency.append([])
                    self.digital_latency.append([])
                    self.intra_tile_latency.append([])
                    self.inter_tile_latency.append([])
                    self.tile_merge_latency.append([])
                    self.tile_transfer_latency.append([])
                    output_size = list(map(int, layer_dict['Outputsize']))
                    input_size = list(map(int, layer_dict['Inputsize']))
                    kernelsize = int(layer_dict['Kernelsize'])
                    stride = int(layer_dict['Stride'])
                    inputchannel = int(layer_dict['Inputchannel'])
                    outputchannel = int(layer_dict['Outputchannel'])
                    padding = int(layer_dict['Padding'])
                    inputbit = int(layer_dict['Inputbit'])
                    outputbit = int(layer_dict['outputbit'])
                    # print(self.graph.layer_tileinfo[layer_id]['max_row'])
                    input_channel_PE = self.graph.layer_tileinfo[layer_id]['max_row'] / (kernelsize ** 2)
                    # the input channel number each PE processes
                    temp_tile_latency = tile_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                              read_row=self.graph.layer_tileinfo[layer_id]['max_row'],
                                                              read_column=self.graph.layer_tileinfo[layer_id]['max_column'],
                                                              indata=0, rdata=0, inprecision=inputbit,
                                                              PE_num=self.graph.layer_tileinfo[layer_id]['max_PE']
                                                              )
                    # merge_time = self.graph.inLayer_distance[0][layer_id] * (temp_tile_latency.digital_period +
                    #                                                          self.graph.layer_tileinfo[layer_id]['max_column'] *
                    #                                                          outputbit / self.inter_tile_bandwidth)
                    merge_time = (self.graph.layer_tileinfo[layer_id][
                                      'tilenum'] - 1) * temp_tile_latency.digital_period + \
                                 self.graph.inLayer_distance[0][layer_id] * self.graph.layer_tileinfo[layer_id][
                                     'max_column'] * outputbit / self.inter_tile_bandwidth

                    # Todo: update merge time (adder tree) and transfer data volume
                    transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            outputchannel * outputbit / self.inter_tile_bandwidth)
                    # Todo: update transfer data volume
                    last_layer_finish_time = self.finish_time[layer_id-1][-1]
                    for i in range(output_size[0]):
                        for j in range(output_size[1]):
                            last_layer_pos = (min(kernelsize + stride * i - padding, input_size[0]) - 1) * input_size[
                                1] + \
                                             min(kernelsize + stride * j - padding, input_size[1]) - 1
                            # last_layer_pos = min((kernelsize + stride * i - padding - 1) * input_size[1] + \
                            #                  kernelsize + stride * j - padding - 1, len(self.finish_time[layer_id-1])-1)
                            if last_layer_pos > len(self.finish_time[layer_id-1])-1:
                                print("pos error", i,j)
                            if (i == 0) & (j == 0):
                                # the first output
                                indata = input_channel_PE * (input_size[1] * max(kernelsize - padding - 1, 0) + max(
                                    kernelsize - padding, 0))*inputbit/8
                                # fill the line buffer
                                rdata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                                # from the line buffer to the input reg
                                temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                begin_time = last_layer_finish_time
                                compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + \
                                               begin_time
                                # consider the input data generation time
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                self.compute_interval[layer_id].append([begin_time, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                      temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                      temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)
                                # print(self.finish_time[layer_id])
                            elif j == 0:
                                indata = input_channel_PE * stride * max(kernelsize - padding, 0)*inputbit/8
                                # line feed in line buffer
                                rdata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                                # from the line buffer to the input reg
                                temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                begin_time = self.finish_time[layer_id][(i - 1) * output_size[1] + output_size[1] - 1]
                                # max (the required input data generation time, previous point computation complete time)
                                compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + \
                                               begin_time
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                self.compute_interval[layer_id].append([begin_time, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                      temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                      temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)
                                # print(self.finish_time[layer_id])
                            else:
                                indata = input_channel_PE * stride ** 2*inputbit/8
                                # write new input data to line buffer
                                rdata = stride * kernelsize * input_channel_PE*inputbit/8
                                temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                begin_time = self.finish_time[layer_id][i * output_size[1] + j - 1]
                                # max (the required input data generation time, previous point computation complete time)
                                compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + \
                                               begin_time
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                self.compute_interval[layer_id].append([begin_time, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                      temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                      temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)
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
                    self.compute_interval.append([])

                    self.buffer_latency.append([])
                    self.computing_latency.append([])
                    self.DAC_latency.append([])
                    self.xbar_latency.append([])
                    self.ADC_latency.append([])
                    self.digital_latency.append([])
                    self.intra_tile_latency.append([])
                    self.inter_tile_latency.append([])
                    self.tile_merge_latency.append([])
                    self.tile_transfer_latency.append([])
                    indata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                    rdata = indata*inputbit/8
                    temp_tile_latency = tile_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                              read_row=self.graph.layer_tileinfo[layer_id]['max_row'],
                                                              read_column=self.graph.layer_tileinfo[layer_id]['max_column'],
                                                              indata=indata, rdata=rdata, inprecision=inputbit,
                                                              PE_num=self.graph.layer_tileinfo[layer_id]['max_PE']
                                                              )
                    # merge_time = self.graph.inLayer_distance[0][layer_id] * (temp_tile_latency.digital_period +
                    #                                                          self.graph.layer_tileinfo[layer_id]['max_column'] *
                    #                                                          outputbit / self.inter_tile_bandwidth)
                    merge_time = (self.graph.layer_tileinfo[layer_id][
                                      'tilenum'] - 1) * temp_tile_latency.digital_period + \
                                 self.graph.inLayer_distance[0][layer_id] * self.graph.layer_tileinfo[layer_id][
                                     'max_column'] * outputbit / self.inter_tile_bandwidth

                    # Todo: update merge time (adder tree) and transfer data volume
                    transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            output_size * outputbit / self.inter_tile_bandwidth)
                    begin_time = self.finish_time[layer_id-1][-1]
                    compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + begin_time
                    self.begin_time[layer_id] = output_size * [begin_time]
                    self.finish_time[layer_id]= output_size*[compute_time]
                    self.compute_interval[layer_id].append([begin_time, compute_time])

                    self.buffer_latency[layer_id].append(
                        temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                    self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                    self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                    self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                    self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                    self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                          temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                          temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                    self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                    self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                    self.tile_merge_latency[layer_id].append(merge_time)
                    self.tile_transfer_latency[layer_id].append(transfer_time)
                    # print("start time: ",self.begin_time[layer_id])
                    # print("finish time:",self.finish_time[layer_id])
                    # print('==============================')
                else:
                    assert layer_dict['type'] == 'pooling', "Layer type can only be conv/fc/pooling"
                    self.begin_time.append([])
                    self.finish_time.append([])
                    self.compute_interval.append([])

                    self.buffer_latency.append([])
                    self.computing_latency.append([])
                    self.DAC_latency.append([])
                    self.xbar_latency.append([])
                    self.ADC_latency.append([])
                    self.digital_latency.append([])
                    self.intra_tile_latency.append([])
                    self.inter_tile_latency.append([])
                    self.tile_merge_latency.append([])
                    self.tile_transfer_latency.append([])
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
                    # Todo: update merge time of pooling tile
                    transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            outputchannel * outputbit / self.inter_tile_bandwidth)
                    # Todo: update transfer data volume
                    for i in range(output_size[0]):
                        for j in range(output_size[1]):
                            if (i == 0) & (j == 0):
                                # the first output
                                indata = inputchannel * (input_size[1] * max(kernelsize - padding - 1, 0) + max(
                                    kernelsize - padding, 0))*inputbit/8
                                # fill the line buffer
                                rdata = inputchannel*kernelsize**2*inputbit/8
                                # from the line buffer to the input reg
                                temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)
                                begin_time = self.finish_time[layer_id - 1][-1]
                                compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + \
                                               begin_time
                                # consider the input data generation time
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                self.compute_interval[layer_id].append([begin_time, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_pooling_latency.buf_wlatency + temp_pooling_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(0)
                                self.DAC_latency[layer_id].append(0)
                                self.xbar_latency[layer_id].append(0)
                                self.ADC_latency[layer_id].append(0)
                                self.digital_latency[layer_id].append(temp_pooling_latency.digital_period)
                                    # TODO: update pooling latency analysis
                                self.intra_tile_latency[layer_id].append(0)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)
                                # print(self.finish_time[layer_id])
                            elif j == 0:
                                indata = inputchannel * stride * max(kernelsize - padding, 0)*inputbit/8
                                # line feed in line buffer
                                rdata = inputchannel*kernelsize**2*inputbit/8
                                # from the line buffer to the input reg
                                temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)
                                begin_time = self.finish_time[layer_id][(i - 1) * output_size[1] + output_size[1] - 1]
                                compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + \
                                               begin_time
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                self.compute_interval[layer_id].append([begin_time, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_pooling_latency.buf_wlatency + temp_pooling_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(0)
                                self.DAC_latency[layer_id].append(0)
                                self.xbar_latency[layer_id].append(0)
                                self.ADC_latency[layer_id].append(0)
                                self.digital_latency[layer_id].append(temp_pooling_latency.digital_period)
                                # TODO: update pooling latency analysis
                                self.intra_tile_latency[layer_id].append(0)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)
                                # print(self.finish_time[layer_id])
                            else:
                                indata = inputchannel * stride ** 2*inputbit/8
                                # write new input data to line buffer
                                rdata = stride * kernelsize * inputchannel*inputbit/8
                                temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)
                                begin_time = self.finish_time[layer_id][i * output_size[1] + j - 1]
                                compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + \
                                               begin_time
                                self.begin_time[layer_id].append(begin_time)
                                self.finish_time[layer_id].append(compute_time)
                                self.compute_interval[layer_id].append([begin_time, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_pooling_latency.buf_wlatency + temp_pooling_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(0)
                                self.DAC_latency[layer_id].append(0)
                                self.xbar_latency[layer_id].append(0)
                                self.ADC_latency[layer_id].append(0)
                                self.digital_latency[layer_id].append(temp_pooling_latency.digital_period)
                                # TODO: update pooling latency analysis
                                self.intra_tile_latency[layer_id].append(0)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)
                    # print("start time: ",self.begin_time[layer_id])
                    # print("finish time:",self.finish_time[layer_id])
                    # print('==============================')
            self.compute_interval[layer_id] = merge_interval(self.compute_interval[layer_id])
            temp_runtime = 0
            for l in range(len(self.compute_interval[layer_id])):
                temp_runtime += (self.compute_interval[layer_id][l][1]-self.compute_interval[layer_id][l][0])
            self.occupancy.append(temp_runtime/(max(self.finish_time[layer_id])-min(self.begin_time[layer_id])))
            self.total_buffer_latency.append(sum(self.buffer_latency[layer_id]))
            self.total_computing_latency.append(sum(self.computing_latency[layer_id]))
            self.total_DAC_latency.append(sum(self.DAC_latency[layer_id]))
            self.total_xbar_latency.append(sum(self.xbar_latency[layer_id]))
            self.total_ADC_latency.append(sum(self.ADC_latency[layer_id]))
            self.total_digital_latency.append(sum(self.digital_latency[layer_id]))
            self.total_inter_tile_latency.append(sum(self.inter_tile_latency[layer_id]))
            self.total_intra_tile_latency.append(sum(self.intra_tile_latency[layer_id]))
            self.total_tile_merge_latency.append(sum(self.tile_merge_latency[layer_id]))
            self.total_tile_transfer_latency.append(sum(self.tile_transfer_latency[layer_id]))

    def Latency_stall_calculate(self):
        ''' should be used after the calculate_model '''
        Linebuffer_Size = 2048 # Bytes
        OutputBuffer_Size = 32*1024 # Bytes
        layer_occu = []
        for layer_id in range(len(self.NetStruct)):
            layer_dict = self.NetStruct[layer_id][0][0]
            self.layer_type.append(layer_dict['type'])
            if (self.occupancy[layer_id] == 1) and (layer_dict['type'] == 'conv'):
            # if ((self.occupancy[layer_id] == 1) and (layer_dict['type'] == 'conv')) or (layer_dict['type'] == 'pooling'):
                layer_occu.append(layer_id)
        ''' check the consecuive of the layer '''
        if len(layer_occu) is 0:
            return
        print(layer_occu)
        layer_stall = []
        start = layer_occu[0]
        end = start
        for i in range(len(layer_occu)-1):
            if layer_occu[i+1] == layer_occu[i]+1:
                end = layer_occu[i+1]
            else:
                if start < end:
                    layer_stall.append([start, end])
                start = layer_occu[i+1]
                end = start
        if end > start:
            layer_stall.append([start, end])
        if len(layer_stall) == 0:
            print("No need to be stalled")
            return
        else:
            # print(layer_stall)
            for i in range(len(layer_stall)):
                for layer_id in range(layer_stall[i][1], layer_stall[i][0], -1):
                    layer_dict = self.NetStruct[layer_id][0][0]
                    output_size = list(map(int, layer_dict['Outputsize']))
                    input_size = list(map(int, layer_dict['Inputsize']))
                    kernelsize = int(layer_dict['Kernelsize'])
                    stride = int(layer_dict['Stride'])
                    inputchannel = int(layer_dict['Inputchannel'])
                    outputchannel = int(layer_dict['Outputchannel'])
                    padding = int(layer_dict['Padding'])
                    inputbit = int(layer_dict['Inputbit'])
                    outputbit = int(layer_dict['outputbit'])
                    input_channel_PE = self.graph.layer_tileinfo[layer_id]['max_row'] / (kernelsize ** 2)
                    ''' get the point number of this layer and then go back to the previous layer '''
                    # TODO: update the tile usage of this
                    tile_num = self.graph.layer_tileinfo[layer_id]['tilenum']
                    pre_point = 0
                    cur_point = 0
                    res = 0
                    if layer_dict['type'] == 'conv':
                        storage_capacity = Linebuffer_Size / input_channel_PE + OutputBuffer_Size * tile_num / outputchannel
                    else:
                        storage_capacity = Linebuffer_Size / inputchannel + OutputBuffer_Size * tile_num / outputchannel
                    # print("Storage is: ", storage_capacity)
                    for cur_point in range(len(self.begin_time[layer_id])):
                        cur_row = cur_point // output_size[1] # begin from 0
                        cur_column = cur_point - cur_row * output_size[1] # begin from 0
                        used_point = (stride * cur_row - padding) * input_size[1] + \
                                     (cur_column * stride - padding) * stride
                        pre_point = Search(self.begin_time[layer_id][cur_point], self.begin_time[layer_id - 1])
                        # begin from 1
                        res = storage_capacity - (pre_point + cur_point - used_point)
                        # print(res)
                        if res <= 0:
                            print("You need to stall the Pipeline on Layer %d" % (layer_id -1))
                            break
                    # update the stall time
                    if res > 0:
                        print("No need to be stalled")
                        continue
                    else:
                        pre_point = pre_point - 1
                        # print(pre_point)
                        while (pre_point < input_size[0] * input_size[1]):
                            delta = self.begin_time[layer_id][cur_point] - self.begin_time[layer_id - 1][pre_point]
                            assert delta > 0, "delta is not 0, something error"
                            # self.begin_time[layer_id - 1][pre_point] = self.begin_time[layer_id][cur_point]
                            consumption = stride ** 2
                            for num in range(consumption):
                                self.begin_time[layer_id - 1][pre_point + num] += delta
                                self.finish_time[layer_id - 1][pre_point + num] += delta
                                pre_point += consumption
                            cur_point += 1
                        interval = []
                        for i in range(len(self.begin_time[layer_id - 1])):
                            interval.append([self.begin_time[layer_id - 1][i], self.finish_time[layer_id - 1][i]])
                        stall_interval = merge_interval(interval)
                        self.compute_interval[layer_id-1] = stall_interval
                        print("++++++++++++++++++++++++++++++++")
                        print("updated: ", self.begin_time[layer_id - 1])
                        print("         ", self.finish_time[layer_id - 1])
                        print("         ",  self.compute_interval[layer_id-1])
                        print(len(stall_interval))
        return

    def model_latency_output(self, module_information=1, layer_information = 1):
        print(' ')
        if(layer_information):
            for i in range(len(self.begin_time)):
                print("Layer", i, " type:", self.NetStruct[i][0][0]['type'])
                # print("start time: ", self.begin_time[i])
                # print("finish time:", self.finish_time[i])
                # print("Time interval of working:", self.compute_interval[i])
                print("Occupancy:", self.occupancy[i])
                #     # print(self.xbar_latency[i])
                total_latency = self.total_buffer_latency[i] + self.total_computing_latency[i] + \
                                self.total_digital_latency[i] + self.total_intra_tile_latency[i] + \
                                self.total_inter_tile_latency[i]
                if(module_information):
                    print("Buffer latency of layer", i, ":", self.total_buffer_latency[i], '(',
                          "%.2f" % (100 * self.total_buffer_latency[i] / total_latency), '%)')
                    print("Computing latency of layer", i, ":", self.total_computing_latency[i], '(',
                          "%.2f" % (100 * self.total_computing_latency[i] / total_latency), '%)')
                    print("     DAC latency of layer", i, ":", self.total_DAC_latency[i], '(',
                          "%.2f" % (100 * self.total_DAC_latency[i] / total_latency), '%)')
                    print("     ADC latency of layer", i, ":", self.total_ADC_latency[i], '(',
                          "%.2f" % (100 * self.total_ADC_latency[i] / total_latency), '%)')
                    print("     xbar latency of layer", i, ":", self.total_xbar_latency[i], '(',
                          "%.2f" % (100 * self.total_xbar_latency[i] / total_latency), '%)')
                    print("Digital part latency of layer", i, ":", self.total_digital_latency[i], '(',
                          "%.2f" % (100 * self.total_digital_latency[i] / total_latency), '%)')
                    print("Intra tile communication latency of layer", i, ":", self.total_intra_tile_latency[i], '(',
                          "%.2f" % (100 * self.total_intra_tile_latency[i] / total_latency), '%)')
                    print("Inter tile communication latency of layer", i, ":", self.total_inter_tile_latency[i], '(',
                          "%.2f" % (100 * self.total_inter_tile_latency[i] / total_latency), '%)')
                    print("     One layer merge latency of layer", i, ":", self.total_tile_merge_latency[i], '(',
                          "%.2f" % (100 * self.total_tile_merge_latency[i] / total_latency), '%)')
                    print("     Inter tile transfer latency of layer", i, ":", self.total_tile_transfer_latency[i], '(',
                          "%.2f" % (100 * self.total_tile_transfer_latency[i] / total_latency), '%)')
                print('----------------------------------------------')
        # print("Latency simulation finished!")
        print("Entire latency:", max(max(self.finish_time)), "ns")

    def calculate_model_latency(self, mode=0):
        ''' merge the latency_0 and latency_1 '''
        for layer_id in range(len(self.NetStruct)):
            layer_dict = self.NetStruct[layer_id][0][0]
            if layer_id == 0:
                # for the first layer, first layer must be conv layer
                self.begin_time.append([])
                self.finish_time.append([])
                self.compute_interval.append([])

                self.buffer_latency.append([])
                self.computing_latency.append([])
                self.DAC_latency.append([])
                self.xbar_latency.append([])
                self.ADC_latency.append([])
                self.digital_latency.append([])
                self.intra_tile_latency.append([])
                self.inter_tile_latency.append([])
                self.tile_merge_latency.append([])
                self.tile_transfer_latency.append([])
                output_size = list(map(int, layer_dict['Outputsize']))
                input_size = list(map(int, layer_dict['Inputsize']))
                kernelsize = int(layer_dict['Kernelsize'])
                stride = int(layer_dict['Stride'])
                inputchannel = int(layer_dict['Inputchannel'])
                outputchannel = int(layer_dict['Outputchannel'])
                padding = int(layer_dict['Padding'])
                inputbit = int(layer_dict['Inputbit'])
                outputbit = int(layer_dict['outputbit'])
                # print(self.graph.layer_tileinfo[layer_id]['max_row'])
                input_channel_PE = self.graph.layer_tileinfo[layer_id]['max_row'] / (kernelsize ** 2)
                # the input channel number each PE processes
                temp_tile_latency = tile_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                          read_row=self.graph.layer_tileinfo[layer_id]['max_row'],
                                                          read_column=self.graph.layer_tileinfo[layer_id]['max_column'],
                                                          indata=0, rdata=0, inprecision=inputbit,
                                                          PE_num=self.graph.layer_tileinfo[layer_id]['max_PE']
                                                          )
                # merge_time = self.graph.inLayer_distance[0][layer_id] * (temp_tile_latency.digital_period +
                #                                                          self.graph.layer_tileinfo[layer_id][
                #                                                              'max_column'] * outputbit / self.inter_tile_bandwidth)
                merge_time = (self.graph.layer_tileinfo[layer_id]['tilenum'] - 1) * temp_tile_latency.digital_period + \
                             self.graph.inLayer_distance[0][layer_id] * self.graph.layer_tileinfo[layer_id][
                                 'max_column'] * outputbit / self.inter_tile_bandwidth
                # Todo: update merge time (adder tree) and transfer data volume
                transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                        outputchannel * outputbit / self.inter_tile_bandwidth)

                cur_multiple = self.multiple[layer_id]
                split_size = Split_map(padding=padding, outputsize=output_size[1], multiple=cur_multiple)
                self.layer_split.append(split_size)
                max_time = 0
                # Todo: update transfer data volume
                for i in range(output_size[0]):
                    self.pre_max_time = max_time
                    max_time = 0
                    for m in range(cur_multiple):
                        for j in range(split_size[m]):
                            if (i == 0) & (j == 0):
                                # the first output
                                if m == 0:
                                    indata = input_channel_PE * (split_size[m] * max(kernelsize - padding - 1, 0) +
                                                                 max(kernelsize - padding, 0)) * inputbit / 8
                                else:
                                    indata = input_channel_PE * (split_size[m] * max(kernelsize - padding - 1, 0) +
                                                                 kernelsize) * inputbit / 8
                                # indata = input_channel_PE * (
                                #             input_size[1] * max(kernelsize - padding - 1, 0) + max(kernelsize - padding,
                                #                                                                    0)) * inputbit / 8
                                # fill the line buffer
                                rdata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                                temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time

                                self.begin_time[0].append(0)
                                self.finish_time[0].append(compute_time)
                                self.compute_interval[0].append([0, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                      temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                      temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)
                            elif j == 0:
                                if mode is 0:
                                    indata = inputbit / 8 * input_channel_PE * (
                                                input_size[1] * (stride - 1) + max(kernelsize - padding, 0))
                                elif mode is 1:
                                    indata = inputbit / 8 * input_channel_PE * stride * max(kernelsize - padding, 0)
                                else:
                                    assert mode == 2, "the mode can only be 0/1/2"
                                    if m == 0:
                                        indata = input_channel_PE * stride * max(kernelsize - padding, 0) * inputbit / 8
                                    else:
                                        indata = input_channel_PE * stride * kernelsize * inputbit / 8
                                rdata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                                temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                # TODO: Check
                                # if mode == 2:
                                #     begin_time = self.pre_max_time
                                # else:
                                #     begin_time = self.finish_time[0][(i - 1) * output_size[1] + output_size[1] - 1]
                                begin_time = self.pre_max_time
                                compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + begin_time
                                self.begin_time[0].append(begin_time)
                                self.finish_time[0].append(compute_time)
                                self.compute_interval[0].append([begin_time, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                      temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                      temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)
                            else:
                                rdata = stride * kernelsize * input_channel_PE * inputbit / 8
                                if mode is 0:
                                    indata = input_channel_PE * stride * inputbit / 8
                                    # temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                    # begin_time = self.finish_time[0][i * output_size[1] + j - 1]
                                else:
                                    indata = input_channel_PE * stride ** 2 * inputbit / 8
                                temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                if mode == 2:
                                    begin_time = self.finish_time[0][-1]
                                else:
                                    begin_time = self.finish_time[0][i * output_size[1] + j - 1]
                                compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + begin_time
                                self.begin_time[0].append(begin_time)
                                self.finish_time[0].append(compute_time)
                                self.compute_interval[0].append([begin_time, compute_time])

                                self.buffer_latency[layer_id].append(
                                    temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                      temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                      temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                self.tile_merge_latency[layer_id].append(merge_time)
                                self.tile_transfer_latency[layer_id].append(transfer_time)

                                if j == split_size[m] - 1:
                                    if max_time < self.finish_time[0][-1]:
                                        max_time = self.finish_time[0][-1]
            else:
                if layer_dict['type'] is 'conv':
                    self.begin_time.append([])
                    self.finish_time.append([])
                    self.compute_interval.append([])

                    self.buffer_latency.append([])
                    self.computing_latency.append([])
                    self.DAC_latency.append([])
                    self.xbar_latency.append([])
                    self.ADC_latency.append([])
                    self.digital_latency.append([])
                    self.intra_tile_latency.append([])
                    self.inter_tile_latency.append([])
                    self.tile_merge_latency.append([])
                    self.tile_transfer_latency.append([])
                    output_size = list(map(int, layer_dict['Outputsize']))
                    input_size = list(map(int, layer_dict['Inputsize']))
                    kernelsize = int(layer_dict['Kernelsize'])
                    stride = int(layer_dict['Stride'])
                    inputchannel = int(layer_dict['Inputchannel'])
                    outputchannel = int(layer_dict['Outputchannel'])
                    padding = int(layer_dict['Padding'])
                    inputbit = int(layer_dict['Inputbit'])
                    outputbit = int(layer_dict['outputbit'])
                    input_channel_PE = self.graph.layer_tileinfo[layer_id]['max_row'] / (kernelsize ** 2)
                    # the input channel number each PE processes
                    temp_tile_latency = tile_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                              read_row=self.graph.layer_tileinfo[layer_id]['max_row'],
                                                              read_column=self.graph.layer_tileinfo[layer_id][
                                                                  'max_column'],
                                                              indata=0, rdata=0, inprecision=inputbit,
                                                              PE_num=self.graph.layer_tileinfo[layer_id]['max_PE']
                                                              )
                    merge_time = (self.graph.layer_tileinfo[layer_id][
                                      'tilenum'] - 1) * temp_tile_latency.digital_period + \
                                 self.graph.inLayer_distance[0][layer_id] * self.graph.layer_tileinfo[layer_id][
                                     'max_column'] * outputbit / self.inter_tile_bandwidth
                    # Todo: update merge time (adder tree) and transfer data volume
                    transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                            outputchannel * outputbit / self.inter_tile_bandwidth)
                    # Todo: update transfer data volume
                    ''' get the multiple for the conv layer '''
                    cur_multiple = self.multiple[layer_id]
                    split_size = Split_map(padding=padding, outputsize=output_size[1], multiple=cur_multiple)
                    self.layer_split.append(split_size)
                    max_time = 0
                    for i in range(output_size[0]):
                        self.pre_max_time = max_time
                        max_time = 0
                        cur_column = 0
                        for m in range(cur_multiple):
                            for j in range(split_size[m]):
                                last_layer_pos = (min(kernelsize + stride * i - padding, input_size[0]) - 1) * input_size[
                                    1] + min(kernelsize + stride * j - padding, input_size[1]) - 1
                                if last_layer_pos > len(self.finish_time[layer_id - 1]) - 1:
                                    print("pos error", i, j)
                                if (i == 0) & (j == 0):
                                    ''' the first output '''
                                    if m == 0:
                                        indata = input_channel_PE * (split_size[m] * max(kernelsize - padding - 1, 0) +
                                                                     max(kernelsize - padding, 0)) * inputbit / 8
                                    else:
                                        indata = input_channel_PE * (split_size[m] * max(kernelsize - padding - 1, 0) +
                                                                     kernelsize) * inputbit / 8
                                    rdata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                                    temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                    begin_time = self.finish_time[layer_id - 1][last_layer_pos]
                                    compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + begin_time
                                    self.begin_time[layer_id].append(begin_time)
                                    self.finish_time[layer_id].append(compute_time)
                                    self.compute_interval[layer_id].append([begin_time, compute_time])

                                    self.buffer_latency[layer_id].append(
                                        temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                    self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                    self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                    self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                    self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                    self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                          temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                          temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                    self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                    self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                    self.tile_merge_latency[layer_id].append(merge_time)
                                    self.tile_transfer_latency[layer_id].append(transfer_time)

                                elif j == 0:
                                    rdata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                                    if mode == 0:
                                        indata = inputbit / 8 * input_channel_PE * (input_size[1] * (stride - 1) +
                                                                                    max(kernelsize - padding, 0))
                                    elif mode == 1:
                                        indata = input_channel_PE * stride * max(kernelsize - padding, 0) * inputbit / 8
                                    else:
                                        if m== 0:
                                            indata = input_channel_PE * stride * max(kernelsize - padding,
                                                                                     0) * inputbit / 8
                                        else:
                                            indata = input_channel_PE * stride * kernelsize * inputbit / 8

                                    temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                    longest_time_pos = self.Judge(last_layer_pos, layer_id)
                                    if m == 0:
                                        begin_time = max(self.finish_time[layer_id - 1][last_layer_pos],
                                                         self.pre_max_time)
                                    else:
                                        begin_time = max(self.finish_time[layer_id - 1][longest_time_pos],
                                                         self.pre_max_time)
                                    compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + begin_time
                                    self.begin_time[layer_id].append(begin_time)
                                    self.finish_time[layer_id].append(compute_time)
                                    self.compute_interval[layer_id].append([begin_time, compute_time])
                                    self.buffer_latency[layer_id].append(
                                        temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                    self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                    self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                    self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                    self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                    self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                          temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                          temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                    self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                    self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                    self.tile_merge_latency[layer_id].append(merge_time)
                                    self.tile_transfer_latency[layer_id].append(transfer_time)
                                else:
                                    rdata = stride * kernelsize * input_channel_PE * inputbit / 8
                                    if mode == 0:
                                        indata = input_channel_PE * stride * inputbit / 8
                                    else:
                                        indata = input_channel_PE * stride ** 2 * inputbit / 8

                                    temp_tile_latency.update_tile_latency(indata=indata, rdata=rdata)
                                    longest_time_pos = self.Judge(last_layer_pos, layer_id)
                                    # begin_time = max(self.finish_time[layer_id - 1][last_layer_pos],
                                    #                  self.finish_time[layer_id][i * output_size[1] + j - 1])
                                    begin_time = max(self.finish_time[layer_id][-1],
                                                     self.finish_time[layer_id - 1][longest_time_pos])
                                    compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + begin_time
                                    self.begin_time[layer_id].append(begin_time)
                                    self.finish_time[layer_id].append(compute_time)
                                    self.compute_interval[layer_id].append([begin_time, compute_time])

                                    self.buffer_latency[layer_id].append(
                                        temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                                    self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                                    self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                                    self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                                    self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                                    self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                                          temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                                          temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                                    self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                                    self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                    self.tile_merge_latency[layer_id].append(merge_time)
                                    self.tile_transfer_latency[layer_id].append(transfer_time)

                                    if j == split_size[m] - 1:
                                        if max_time < self.finish_time[layer_id][-1]:
                                            max_time = self.finish_time[layer_id][-1]

                            cur_column += split_size[m]
                else:
                    cur_multiple = self.multiple[layer_id]
                    assert cur_multiple == 1, "Only the conv layer can be multipled"
                    if layer_dict['type'] == 'fc':
                        output_size = int(layer_dict['Outfeature'])
                        input_size = int(layer_dict['Infeature'])
                        self.layer_split.append([input_size])

                        inputbit = int(layer_dict['Inputbit'])
                        outputbit = int(layer_dict['outputbit'])
                        self.begin_time.append([])
                        self.finish_time.append([])
                        self.compute_interval.append([])

                        self.buffer_latency.append([])
                        self.computing_latency.append([])
                        self.DAC_latency.append([])
                        self.xbar_latency.append([])
                        self.ADC_latency.append([])
                        self.digital_latency.append([])
                        self.intra_tile_latency.append([])
                        self.inter_tile_latency.append([])
                        self.tile_merge_latency.append([])
                        self.tile_transfer_latency.append([])
                        indata = self.graph.layer_tileinfo[layer_id]['max_row'] * inputbit / 8
                        rdata = indata * inputbit / 8
                        temp_tile_latency = tile_latency_analysis(SimConfig_path=self.SimConfig_path,
                                                                  read_row=self.graph.layer_tileinfo[layer_id]['max_row'],
                                                                  read_column=self.graph.layer_tileinfo[layer_id][
                                                                      'max_column'],
                                                                  indata=indata, rdata=rdata, inprecision=inputbit,
                                                                  PE_num=self.graph.layer_tileinfo[layer_id]['max_PE']
                                                                  )
                        merge_time = (self.graph.layer_tileinfo[layer_id][
                                          'tilenum'] - 1) * temp_tile_latency.digital_period + \
                                     self.graph.inLayer_distance[0][layer_id] * self.graph.layer_tileinfo[layer_id][
                                         'max_column'] * outputbit / self.inter_tile_bandwidth
                        # Todo: update merge time (adder tree) and transfer data volume
                        transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                                output_size * outputbit / self.inter_tile_bandwidth)
                        begin_time = self.finish_time[layer_id - 1][-1]
                        compute_time = temp_tile_latency.tile_latency + merge_time + transfer_time + begin_time
                        self.begin_time[layer_id] = output_size * [begin_time]
                        self.finish_time[layer_id] = output_size * [compute_time]
                        self.compute_interval[layer_id].append([begin_time, compute_time])

                        self.buffer_latency[layer_id].append(
                            temp_tile_latency.buf_wlatency + temp_tile_latency.buf_rlatency)
                        self.computing_latency[layer_id].append(temp_tile_latency.computing_latency)
                        self.DAC_latency[layer_id].append(temp_tile_latency.DAC_latency)
                        self.xbar_latency[layer_id].append(temp_tile_latency.xbar_latency)
                        self.ADC_latency[layer_id].append(temp_tile_latency.ADC_latency)
                        self.digital_latency[layer_id].append(temp_tile_latency.inPE_add_latency +
                                                              temp_tile_latency.ireg_latency + temp_tile_latency.shiftadd_latency +
                                                              temp_tile_latency.oreg_latency + temp_tile_latency.merge_latency)
                        self.intra_tile_latency[layer_id].append(temp_tile_latency.transfer_latency)
                        self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                        self.tile_merge_latency[layer_id].append(merge_time)
                        self.tile_transfer_latency[layer_id].append(transfer_time)
                    else:
                        assert layer_dict['type'] == 'pooling', "Layer type can only be conv/fc/pooling"
                        self.begin_time.append([])
                        self.finish_time.append([])
                        self.compute_interval.append([])

                        self.buffer_latency.append([])
                        self.computing_latency.append([])
                        self.DAC_latency.append([])
                        self.xbar_latency.append([])
                        self.ADC_latency.append([])
                        self.digital_latency.append([])
                        self.intra_tile_latency.append([])
                        self.inter_tile_latency.append([])
                        self.tile_merge_latency.append([])
                        self.tile_transfer_latency.append([])
                        output_size = list(map(int, layer_dict['Outputsize']))
                        input_size = list(map(int, layer_dict['Inputsize']))

                        self.layer_split.append([input_size[1]])
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
                        # Todo: update merge time of pooling tile
                        transfer_time = self.graph.transLayer_distance[0][layer_id] * (
                                outputchannel * outputbit / self.inter_tile_bandwidth)
                        # Todo: update transfer data volume
                        ''' get the multiple for the conv layer '''
                        cur_multiple = self.multiple[layer_id]
                        split_size = Split_map(padding=padding, outputsize=output_size[1], multiple=cur_multiple)
                        max_time = 0
                        input_split = Split_map(padding=padding, outputsize=input_size[1], multiple=cur_multiple)
                        for i in range(output_size[0]):
                            self.pre_max_time = max_time
                            max_time = 0
                            cur_column = 0
                            for m in range(cur_multiple):
                                for j in range(split_size[m]):
                                    last_layer_pos = (min(kernelsize + stride * i - padding, input_size[0]) - 1) * input_size[
                                        1] + min(kernelsize + stride * j - padding, input_size[1]) - 1
                                    if (i == 0) & (j == 0):
                                        # the first output
                                        if m == 0:
                                            indata = inputchannel * (
                                                    input_split[m] * max(kernelsize - padding - 1, 0) +
                                                    max(kernelsize - padding, 0)) * inputbit / 8
                                        else:
                                            indata = inputchannel * (
                                                    input_split[m] * max(kernelsize - padding - 1, 0) +
                                                    kernelsize) * inputbit / 8
                                        # fill the line buffer
                                        rdata = inputchannel * kernelsize ** 2 * inputbit / 8
                                        # from the line buffer to the input reg
                                        temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)
                                        begin_time = self.finish_time[layer_id - 1][last_layer_pos]
                                        compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + begin_time
                                        self.begin_time[layer_id].append(begin_time)
                                        self.finish_time[layer_id].append(compute_time)
                                        self.compute_interval[layer_id].append([begin_time, compute_time])

                                        self.buffer_latency[layer_id].append(
                                            temp_pooling_latency.buf_wlatency + temp_pooling_latency.buf_rlatency)
                                        self.computing_latency[layer_id].append(0)
                                        self.DAC_latency[layer_id].append(0)
                                        self.xbar_latency[layer_id].append(0)
                                        self.ADC_latency[layer_id].append(0)
                                        self.digital_latency[layer_id].append(temp_pooling_latency.digital_period)
                                        # TODO: update pooling latency analysis
                                        self.intra_tile_latency[layer_id].append(0)
                                        self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                        self.tile_merge_latency[layer_id].append(merge_time)
                                        self.tile_transfer_latency[layer_id].append(transfer_time)
                                    elif j == 0:
                                        if mode == 0:
                                            indata = inputbit / 8 * inputchannel * (input_size[1] * (stride - 1) +
                                                                                    max(kernelsize - padding, 0))
                                        elif mode == 1:
                                            indata = inputchannel * stride * max(kernelsize - padding, 0) * inputbit / 8
                                        else:
                                            if m == 0:
                                                indata = inputchannel * stride * max(kernelsize - padding,
                                                                                     0) * inputbit / 8
                                            else:
                                                indata = inputchannel * stride * kernelsize * inputbit / 8

                                        rdata = inputchannel * kernelsize ** 2 * inputbit / 8
                                        temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)

                                        longest_time_pos = self.Judge(last_layer_pos, layer_id)
                                        # begin_time = max(self.finish_time[layer_id - 1][last_layer_pos],
                                        #                  self.finish_time[layer_id][
                                        #                      (i - 1) * output_size[1] + output_size[1] - 1])
                                        if m == 0:
                                            begin_time = max(self.finish_time[layer_id - 1][last_layer_pos],
                                                             self.pre_max_time)
                                        else:
                                            begin_time = max(self.finish_time[layer_id - 1][longest_time_pos],
                                                             self.pre_max_time)
                                        compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + \
                                                       begin_time
                                        self.begin_time[layer_id].append(begin_time)
                                        self.finish_time[layer_id].append(compute_time)
                                        self.compute_interval[layer_id].append([begin_time, compute_time])

                                        self.buffer_latency[layer_id].append(
                                            temp_pooling_latency.buf_wlatency + temp_pooling_latency.buf_rlatency)
                                        self.computing_latency[layer_id].append(0)
                                        self.DAC_latency[layer_id].append(0)
                                        self.xbar_latency[layer_id].append(0)
                                        self.ADC_latency[layer_id].append(0)
                                        self.digital_latency[layer_id].append(temp_pooling_latency.digital_period)
                                        # TODO: update pooling latency analysis
                                        self.intra_tile_latency[layer_id].append(0)
                                        self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                        self.tile_merge_latency[layer_id].append(merge_time)
                                        self.tile_transfer_latency[layer_id].append(transfer_time)
                                    else:
                                        if mode == 0:
                                            indata = inputchannel * stride * inputbit / 8
                                        else:
                                            indata = inputchannel * stride ** 2 * inputbit / 8
                                        rdata = stride * kernelsize * inputchannel * inputbit / 8
                                        temp_pooling_latency.update_pooling_latency(indata=indata, rdata=rdata)

                                        longest_time_pos = self.Judge(last_layer_pos, layer_id)
                                        begin_time = max(self.finish_time[layer_id][-1],
                                                         self.finish_time[layer_id - 1][longest_time_pos])
                                        compute_time = temp_pooling_latency.pooling_latency + merge_time + transfer_time + \
                                                       begin_time
                                        self.begin_time[layer_id].append(begin_time)
                                        self.finish_time[layer_id].append(compute_time)
                                        self.compute_interval[layer_id].append([begin_time, compute_time])

                                        self.buffer_latency[layer_id].append(
                                            temp_pooling_latency.buf_wlatency + temp_pooling_latency.buf_rlatency)
                                        self.computing_latency[layer_id].append(0)
                                        self.DAC_latency[layer_id].append(0)
                                        self.xbar_latency[layer_id].append(0)
                                        self.ADC_latency[layer_id].append(0)
                                        self.digital_latency[layer_id].append(temp_pooling_latency.digital_period)
                                        # TODO: update pooling latency analysis
                                        self.intra_tile_latency[layer_id].append(0)
                                        self.inter_tile_latency[layer_id].append(merge_time + transfer_time)
                                        self.tile_merge_latency[layer_id].append(merge_time)
                                        self.tile_transfer_latency[layer_id].append(transfer_time)

                                        if j == split_size[m] - 1:
                                            if max_time < self.finish_time[layer_id][-1]:
                                                max_time = self.finish_time[layer_id][-1]

            self.compute_interval[layer_id] = merge_interval(self.compute_interval[layer_id])
            temp_runtime = 0
            for l in range(len(self.compute_interval[layer_id])):
                temp_runtime += (self.compute_interval[layer_id][l][1] - self.compute_interval[layer_id][l][0])
            self.occupancy.append(temp_runtime / (max(self.finish_time[layer_id]) - min(self.begin_time[layer_id])))
            self.total_buffer_latency.append(sum(self.buffer_latency[layer_id]))
            self.total_computing_latency.append(sum(self.computing_latency[layer_id]))
            self.total_DAC_latency.append(sum(self.DAC_latency[layer_id]))
            self.total_xbar_latency.append(sum(self.xbar_latency[layer_id]))
            self.total_ADC_latency.append(sum(self.ADC_latency[layer_id]))
            self.total_digital_latency.append(sum(self.digital_latency[layer_id]))
            self.total_inter_tile_latency.append(sum(self.inter_tile_latency[layer_id]))
            self.total_intra_tile_latency.append(sum(self.intra_tile_latency[layer_id]))
            self.total_tile_merge_latency.append(sum(self.tile_merge_latency[layer_id]))
            self.total_tile_transfer_latency.append(sum(self.tile_transfer_latency[layer_id]))

if __name__ == '__main__':
    test_SimConfig_path = os.path.join(os.path.dirname(os.path.dirname(os.getcwd())), "SimConfig.ini")
    test_weights_file_path = os.path.join(os.path.dirname(os.path.dirname(os.getcwd())),
                                          "alexnet_params.pth")

    __TestInterface = TrainTestInterface('alexnet', 'MNSIM.Interface.cifar10', test_SimConfig_path, test_weights_file_path,
                                         'cpu')
    structure_file = __TestInterface.get_structure()
    test = Model_latency(structure_file, test_SimConfig_path)

    tile = 0
    test.calculate_model_latency(mode=2)
    test.model_latency_output()


