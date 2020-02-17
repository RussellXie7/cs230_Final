#cell 0
import torch
import data_loader
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import os
import json
from collections import defaultdict
# import autoencoder
import numpy as np
import sys
from torch.nn.utils.rnn import pad_sequence

#cell 1
print(torch.cuda.is_available())

def split_ypr(x):
    return x[:,:,0],x[:,:,1], x[:,:,2]
#
# def encode(x, encoder):
#     y,p,r = autoencoder.ae_predict(*split_ypr(x), encoder)
#     return np.stack((y,p,r), axis=2)

def get_dataloader(x, y, batch_size):
    dataset = [(x[i].T, y[i]) for i in range(y.shape[0])]
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
    return dataloader

def pad(input):
    max_length = max(i.shape[0] for i in input)
    for i in range(len(input)):
        result = np.zeros(max_length, 3)
        result[:len(input[i]), 3] = input[i]
        input[i] = result
    return input

def pad_all(trainx, devx, testx, trainy, devy, testy):
    return pad(trainx), pad(devx), pad(testx), pad(trainy), pad(devy), pad(testy)

def acc(data_loader):
    correct = 0
    total = 0
    with torch.no_grad():
        for data in data_loader:
            x, y = data
            if torch.cuda.is_available():
                x = x.cuda()
                y = y.cuda()

            outputs = net(x.float())
            _, predicted = torch.max(outputs.data, 1)

            w = torch.sum((predicted - y) != 0).item()
            r = len(y) - w
            correct += r
            total += len(y)
    return correct / total

def acc_loss(data_loader, criterion):
    correct = 0
    total = 0
    total_loss = 0.0
    with torch.no_grad():
        for data in data_loader:
            x, y = data
            if torch.cuda.is_available():
                x = x.cuda()
                y = y.cuda()

            outputs = net(x.float())
            _, predicted = torch.max(outputs.data, 1)

            w = torch.sum((predicted - y) != 0).item()
            r = len(y) - w
            correct += r
            total += len(y)

            total_loss += criterion(outputs, y.long()).item() * len(x)
    return correct / total, total_loss / total

#cell 7
class Net(nn.Module):
    def __init__(self, input_dim, hidden_dim, n_layers):
        super(Net, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.n_layers = n_layers
        self.lstm = nn.LSTM(input_dim, hidden_dim, n_layers, batch_first=True, bidirectional = True)
        self.fc = nn.Linear(hidden_dim*2, 26, bias = True)

    def forward(self, x):
        init_h = torch.randn(self.n_layers*2, x.shape[0], self.hidden_dim).cuda()
        init_c = torch.randn(self.n_layers*2, x.shape[0], self.hidden_dim).cuda()
        x = x.permute(0, 2, 1)
        out, _ = self.lstm(x, (init_h, init_c))
        # print("inter: ", out.shape)
        out = self.fc(out[:,-1,:])
        # print("out: ", out.shape)
        return out


print(sys.argv[1:])
_, experiment_type, resampled, trial = sys.argv
filename = experiment_type + '_' + resampled + '_' + trial

if experiment_type == "subject":
    if resampled == "resampled":
        trainx, devx, testx, trainy, devy, testy = data_loader.load_all_subject_split(resampled = True, flatten=False)
    else:
        trainx, devx, testx, trainy, devy, testy = data_loader.load_all_subject_split(resampled = False, flatten=False)
        trainx, devx, testx, trainy, devy, testy = pad_all(trainx, devx, testx, trainy, devy, testy)
else:
    if resampled == "resampled":
        trainx, devx, testx, trainy, devy, testy = data_loader.load_all_random_split(resampled = True, flatten=False)
    else:
        trainx, devx, testx, trainy, devy, testy = data_loader.load_all_random_split(resampled = False, flatten=False)
        trainx, devx, testx, trainy, devy, testy = pad_all(trainx, devx, testx, trainy, devy, testy)

print(trainx.shape, devx.shape, testx.shape, trainy.shape, devy.shape, testy.shape)
trainx, trainy = data_loader.augment_train_set(trainx, trainy, augment_prop=3, is_flattened=False)
print(trainx.shape, devx.shape, testx.shape, trainy.shape, devy.shape, testy.shape)

# _,_,_,encoder = autoencoder.ae_denoise(*split_ypr(trainx))
#
#
# trainx = encode(trainx, encoder)
# devx = encode(devx, encoder)
# testx = encode(testx, encoder)
# print(trainx.shape, devx.shape, testx.shape, trainy.shape, devy.shape, testy.shape)
# del encoder

#cell 4
BATCH_SIZE = 250

trainloader = get_dataloader(trainx, trainy, BATCH_SIZE)
devloader = get_dataloader(devx, devy, BATCH_SIZE)
testloader = get_dataloader(testx, testy, BATCH_SIZE)

#cell 5
sample_size, num_feature, num_channel = trainx.shape
print(sample_size, num_feature, num_channel)

#cell 6

net = Net(num_channel, 100, 5)
if torch.cuda.is_available():
    net.cuda()

#cell 8
criterion = nn.CrossEntropyLoss()
# optimizer = optim.SGD(net.parameters(), lr=0.00001, momentum=0.9)
optimizer = optim.AdamW(net.parameters(), weight_decay=0.01)

hist = defaultdict(list)
for epoch in range(1):  # loop over the dataset multiple times
    running_loss = 0.0
    for i, data in enumerate(trainloader):
        print(f'{i if i%20==0 else ""}.', end='')

        # get the inputs; data is a list of [inputs, labels]
        inputs, labels = data
        if torch.cuda.is_available():
            inputs = inputs.cuda()
            labels = labels.cuda()

        # zero the parameter gradients
        optimizer.zero_grad()

        # forward + backward + optimize

        outputs = net(inputs.float())
        loss = criterion(outputs, labels.long())
        loss.backward()
        optimizer.step()

    trainacc, trainloss = acc_loss(trainloader, criterion)
    devacc, devloss = acc_loss(devloader, criterion)
    hist['trainacc'].append(trainacc)
    hist['trainloss'].append(trainloss)
    hist['devacc'].append(devacc)
    hist['devloss'].append(devloss)

    print(f'Epoch {epoch} trainacc={trainacc} devacc={devacc}')
    print(f'        trainloss={trainloss} devloss={devloss}')

print('Finished Training')
torch.save(net.state_dict(), "../saved_model/rnn_bilstm/" + "rnn_bilstm_" + filename + ".pth")

testacc, testloss = acc_loss(testloader, nn.CrossEntropyLoss())
testacc, testloss
hist['testacc'] = testacc
hist['testloss'] = testloss

with open('../output/rnn_bilstm/rnn_' + filename + '.json', 'w') as f:
    json.dump(hist, f)
