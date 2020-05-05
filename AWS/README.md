# AWS Arquitecture

![AWS Arquitecture](https://github.com/incluit/OpenVino-Driver-Management/blob/master/AWS/DriverManagement.png)

## IoT Core

Here we declare all the IoT devices that sends the information to AWS through MQTT messages. Also, the corresponding certificates are generated for apply security to those messages. 

In IoT Core are delaclared the rules that sends information to the others AWS services (ElasticSearch, SNS and DynamoDB)

### IoT Core Rules:

- Send data to ElasticSearch and Kibana: All data in topics /drivers and /actions is sent to Amazon ElasticSearch with an index and ID.
    
- Send a message as an SNS push notification: When a variable registered exceeds a certain value a notification alert is sent.
   
- Insert a message into a DynamoDB table: All messages received in IoT Core is stored in DynamoDB in a no relational table.

## ElasticSearch

The data received from IoT Core is processed by an ElastiSearch cluster and displayed in a Kibana Dashboard.
This dashboard is customizable and adapted to our purpose, with the information of the truck and driver behaviour.

## Cognito

When an user try to access the Kibana Dashboard, have to provide credentials and this are matched with an user pool stored in Amazon Cognito.

## SNS

In Amazon SNS, all the notifications sent from IoT Core are listen by a topic subscribed to an email account.

## DynamoDB

In DynamoDB, two no-relational tables stores all the information as a backup for post processing and data analisys.