from models import AutoEncoder, SimpleNet
import torch
import torch.nn as nn
import numpy as np # for pi constant
import json
import os
from torch.utils.data import DataLoader
from data_load import Dspites, train_val_split
import copy

with open("config.json") as json_file:
    conf = json.load(json_file)

device = conf['train']['device']

dataset_path = os.path.join(conf['data']['dataset_path'], conf['data']['dataset_file'])
dspites_dataset = Dspites(dataset_path)
train_val = train_val_split(dspites_dataset)
val_test = train_val_split(train_val['val'], val_split=0.2)

data_loader_train = DataLoader(train_val['train'], batch_size=conf['train']['batch_size'], shuffle=True, num_workers=2)
data_loader_val = DataLoader(val_test['val'], batch_size=200, shuffle=False, num_workers=1)
data_loader_test = DataLoader(val_test['train'], batch_size=200, shuffle=False, num_workers=1)

print('latent space size:', conf['model']['latent_size'])
print('batch size:', conf['train']['batch_size'])

conf['train']['batch_size'] = 128
data_loader_train = DataLoader(train_val['train'], batch_size=conf['train']['batch_size'], shuffle=True, num_workers=2)
data_loader_val = DataLoader(train_val['val'], batch_size=500, shuffle=False, num_workers=1)

model = AutoEncoder(in_channels=1, dec_channels=1, latent_size=conf['model']['latent_size'])
model = model.to(device)
#
#autoencoder_bce_loss_latent12.pt
model.load_state_dict(torch.load('weights/archi_mega_super_long_metric_learn_6.pt'))

#1 - scale (from 0.5 to 1.0), 2,3 - orientation (cos, sin), 4,5 - position (from 0 to 1)
latent_range = [4,5]
min_value = 0
max_value = 1

regressor = SimpleNet(latent_size=conf['model']['latent_size'], number_of_classes=len(latent_range))
regressor.to(device)

loss_function = nn.MSELoss()
optimizer = torch.optim.Adam(regressor.parameters(), lr=0.001)



def regression_validation(regressor, model, data_loader):
    precision_list = []
    for batch_i, batch in enumerate(data_loader):
        # if batch_i == 500:
        #     break
        label = batch['latent'][:, latent_range]  # figure type
        label = label.type(torch.FloatTensor)
        label = label.type(torch.float32)
        label = label.to(device)
        batch = batch['image'].unsqueeze(1)
        batch = batch.type(torch.float32)
        batch = batch.to(device)

        embedding = model.encode(batch)
        embedding = embedding.detach()
        del batch
        torch.cuda.empty_cache()
        prediction = regressor(embedding)
        prediction[prediction > max_value] = max_value
        prediction[prediction < min_value] = min_value
        error = torch.norm(prediction - label, p=2, dim=1).mean()
        precision_list.append(error)
    mean_precision = sum(precision_list) / len(precision_list)
    return mean_precision



model.eval()
loss_list = []
for epoch in range(45):
   loss_list = []
   regressor.train()
   if epoch > 25:
       for param in optimizer.param_groups:
           param['lr'] = max(0.0001, param['lr'] / 1.2)
           print('lr: ', param['lr'])

   for batch_i, batch in enumerate(data_loader_train):
      label = batch['latent'][:, latent_range]  #coordinates
      label = label.type(torch.float32)
      label = label.to(device)
      batch = batch['image'].unsqueeze(1)
      batch = batch.type(torch.float32)
      batch = batch.to(device)

      embedding = model.encode(batch)
      embedding = embedding.detach()
      del batch
      torch.cuda.empty_cache()
      prediction = regressor(embedding)

      loss = loss_function(prediction, label)
      loss_list.append(loss.item())

      optimizer.zero_grad()
      loss.backward()
      optimizer.step()
   loss = sum(loss_list)/len(loss_list)
   regressor.eval()
   val_error = regression_validation(regressor, model, data_loader_val)
   if epoch == 0:
       min_val_error = val_error
   else:
       min_val_error = min(min_val_error, val_error)
   if min_val_error == val_error:
       best_model = copy.deepcopy(model)
   print('loss: {0:2.4f}, validation error: {1:1.3f}'.format(loss, val_error))

regressor.eval()
test_error = regression_validation(regressor, best_model, data_loader_test)
print('test error: {0:1.3f}'.format(test_error))
