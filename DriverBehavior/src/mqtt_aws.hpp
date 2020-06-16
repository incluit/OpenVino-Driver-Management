#include <functional>
#include <iostream>
#include <fstream>
#include <random>
#include <memory>
#include <chrono>
#include <vector>
#include <string>
#include <utility>
#include <algorithm>
#include <iterator>
#include <map>
#include <thread>
#include <mutex>
#include <math.h>
#include <sys/types.h>
#include <signal.h>

#include <gflags/gflags.h>

#include <aws/crt/Api.h>
#include <aws/crt/Exports.h>
#include <aws/crt/StlAllocator.h>
#include <aws/iot/MqttClient.h>
#include "customflags.hpp"

class MqttAws
{
    public:
    Aws::Crt::ApiHandle apiHandle;

    std::shared_ptr<Aws::Crt::Mqtt::MqttConnection> connection;

    std::condition_variable conditionVariable;
    bool connectionClosed = false;
    bool connectionCompleted = false;
    bool connectionInterrupted = false;
    bool connectionSucceeded = false;

    Aws::Crt::Io::EventLoopGroup eventLoopGroup(1);
    
    Aws::Crt::Io::DefaultHostResolver defaultHostResolver(eventLoopGroup, 1, 5);
    Aws::Crt::Io::ClientBootstrap bootstrap(eventLoopGroup, defaultHostResolver);

    std::mutex mutex;

    std::shared_ptr<Aws::Crt::Mqtt::MqttConnection> Initialize(Aws::Crt::String endpoint,Aws::Crt::String certificatePath,Aws::Crt::String keyPath,Aws::Crt::String caFile,Aws::Crt::String topic,Aws::Crt::String clientId)
    {
        fprintf(stdout, "Initializing..\n");
        if (!eventLoopGroup)
        {
            fprintf(stderr, "Event Loop Group Creation failed with error %s\n", Aws::Crt::ErrorDebugString(eventLoopGroup.LastError()));
            exit(-1);
        }
        if (!bootstrap)
        {
            fprintf(stderr, "ClientBootstrap failed with error %s\n", Aws::Crt::ErrorDebugString(bootstrap.LastError()));
            exit(-1);
        }

        auto clientConfig = Aws::Iot::MqttClientConnectionConfigBuilder(certificatePath.c_str(), keyPath.c_str())
                                .WithEndpoint(endpoint)
                                .WithCertificateAuthority(caFile.c_str())
                                .Build();

        if (!clientConfig)
        {
            fprintf(stderr, "Client Configuration initialization failed with error %s\n", Aws::Crt::ErrorDebugString(Aws::Crt::LastError()));
            exit(-1);
        }

        Aws::Iot::MqttClient mqttClient(bootstrap);
        if (!mqttClient)
        {
            fprintf(stderr, "MQTT Client Creation failed with error %s\n", Aws::Crt::ErrorDebugString(mqttClient.LastError()));
            exit(-1);
        }

        connection = mqttClient.NewConnection(clientConfig);
        if (!*connection)
        {
            fprintf(stderr, "MQTT Connection Creation failed with error %s\n", Aws::Crt::ErrorDebugString(connection->LastError()));
            exit(-1);
        }

        /*
            * This will execute when an mqtt connect has completed or failed.
            */
        auto onConnectionCompleted = [&](Aws::Crt::Mqtt::MqttConnection &, int errorCode, Aws::Crt::Mqtt::ReturnCode returnCode, bool) {
            if (errorCode)
            {
                fprintf(stdout, "Connection failed with error %s\n", Aws::Crt::ErrorDebugString(errorCode));
                std::lock_guard<std::mutex> lockGuard(mutex);
                connectionSucceeded = false;
            }
            else
            {
                fprintf(stdout, "Connection completed with return code %d\n", returnCode);
                connectionSucceeded = true;
            }
            {
                std::lock_guard<std::mutex> lockGuard(mutex);
                connectionCompleted = true;
            }
            conditionVariable.notify_one();
        };

        auto onInterrupted = [&](Aws::Crt::Mqtt::MqttConnection &, int error) {
            fprintf(stdout, "Connection interrupted with error %s\n", Aws::Crt::ErrorDebugString(error));
            connectionInterrupted = true;
        };

        auto onResumed = [&](Aws::Crt::Mqtt::MqttConnection &, Aws::Crt::Mqtt::ReturnCode, bool) {
            fprintf(stdout, "Connection resumed\n");
            connectionInterrupted = false;
        };

        /*
            * Invoked when a disconnect message has completed.
            */
        auto onDisconnect = [&](Aws::Crt::Mqtt::MqttConnection &conn) {
            {
                fprintf(stdout, "Disconnect completed\n");
                std::lock_guard<std::mutex> lockGuard(mutex);
                connectionClosed = true;
            }
            conditionVariable.notify_one();
        };

        connection->OnConnectionCompleted = std::move(onConnectionCompleted);
        connection->OnDisconnect = std::move(onDisconnect);
        connection->OnConnectionInterrupted = std::move(onInterrupted); //I should set a flag here to try to reconnect, probably
        connection->OnConnectionResumed = std::move(onResumed);

        /*
            * Subscribe for incoming publish messages on topic.
            */
        
        auto onPublish = [&](Aws::Crt::Mqtt::MqttConnection &, const Aws::Crt::String &topic, const Aws::Crt::ByteBuf &byteBuf) {
                fprintf(stdout, "Publish received on topic %s\n", topic.c_str());
                fprintf(stdout, "\n Message:\n");
                fwrite(byteBuf.buffer, 1, byteBuf.len, stdout);
                fprintf(stdout, "\n");
            };
        auto onSubAck = [&](Aws::Crt::Mqtt::MqttConnection &, uint16_t packetId, const Aws::Crt::String &topic, Aws::Crt::Mqtt::QOS, int errorCode) {
            if (packetId)
            {
                fprintf(stdout, "Subscribe on topic %s on packetId %d Succeeded\n", topic.c_str(), packetId);
            }
            else
            {
                fprintf(stdout, "Subscribe failed with error %s\n", aws_error_debug_str(errorCode));
            }
            conditionVariable.notify_one();
        };

        /*
            * Actually perform the connect dance.
            * This will use default ping behavior of 1 hour and 3 second timeouts.
            * If you want different behavior, those arguments go into slots 3 & 4.
            */
        fprintf(stdout, "Connecting...\n");
        if (!connection->Connect(clientId.c_str(), false, 20))
        {
            fprintf(stderr, "MQTT Connection failed with error %s\n", Aws::Crt::ErrorDebugString(connection->LastError()));
            exit(-1);
        }
        std::unique_lock<std::mutex> uniqueLock(mutex);
        conditionVariable.wait(uniqueLock, [&]() { return connectionCompleted; });
        if (connectionSucceeded)
        {
            connection->Subscribe(topic.c_str(), AWS_MQTT_QOS_AT_MOST_ONCE, onPublish, onSubAck);
        }
        return connection;
    }

    void publishMessage(std::string input, Aws::Crt::String topic, std::shared_ptr<Aws::Crt::Mqtt::MqttConnection> connection){
        fprintf(stdout, "Publishing..\n");
        Aws::Crt::ByteBuf payload = Aws::Crt::ByteBufNewCopy(Aws::Crt::DefaultAllocator(), (const uint8_t *)input.data(), input.length());
        Aws::Crt::ByteBuf *payloadPtr = &payload;

        if (connectionSucceeded)
        {
            auto onPublish = [&](Aws::Crt::Mqtt::MqttConnection &, const Aws::Crt::String &topic, const Aws::Crt::ByteBuf &byteBuf) {
                fprintf(stdout, "Publish received on topic %s\n", topic.c_str());
                fprintf(stdout, "\n Message:\n");
                fwrite(byteBuf.buffer, 1, byteBuf.len, stdout);
                fprintf(stdout, "\n");
            };

            auto onPublishComplete = [payloadPtr](Aws::Crt::Mqtt::MqttConnection &, uint16_t packetId, int errorCode) {
                fprintf(stdout, "%d\n", errorCode);
                aws_byte_buf_clean_up(payloadPtr);
                if (packetId)
                {
                    fprintf(stdout, "Operation on packetId %d Succeeded\n", packetId);
                }
                else
                {
                    fprintf(stdout, "Operation failed with error %s\n", aws_error_debug_str(errorCode));
                }
            };
            if (connectionInterrupted == false)
            {	
                fprintf(stdout, "%s\n", input.c_str());
                connection->Publish(topic.c_str(), AWS_MQTT_QOS_AT_MOST_ONCE, true, payload, onPublishComplete);
            }
        }
    }

    void unsubscribe(Aws::Crt::String topic){
        fprintf(stdout, "Unsubscrribing..\n");
        if (connectionSucceeded)
        {
            connection->Unsubscribe(
                topic.c_str(), [&](Aws::Crt::Mqtt::MqttConnection &, uint16_t, int) { conditionVariable.notify_one(); });
            //conditionVariable.wait(uniqueLock);
        }
    }

    void disconnect(){
        fprintf(stdout, "Disconnecting..\n");
        if (connectionSucceeded)
        {
            if (connection->Disconnect())
            {
                //conditionVariable.wait(uniqueLock, [&]() { return connectionClosed; });
            }
        }
    }
};
