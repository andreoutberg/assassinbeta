import React from 'react';
import { motion } from 'framer-motion';
import { Activity, BarChart3, Database, ExternalLink } from 'lucide-react';

interface ServiceCard {
  name: string;
  description: string;
  url: string;
  port: number;
  icon: React.ElementType;
  color: string;
}

const System: React.FC = () => {
  const services: ServiceCard[] = [
    {
      name: 'Optuna Dashboard',
      description: 'Strategy optimization & hyperparameter tuning',
      url: '/optuna',
      port: 8080,
      icon: BarChart3,
      color: 'ios-blue',
    },
    {
      name: 'Grafana',
      description: 'System metrics & performance monitoring',
      url: '/grafana',
      port: 3001,
      icon: Activity,
      color: 'ios-orange',
    },
    {
      name: 'Prometheus',
      description: 'Metrics collection & time-series database',
      url: '/prometheus',
      port: 9090,
      icon: Database,
      color: 'ios-red',
    },
  ];

  const openService = (url: string) => {
    // Open service via nginx proxy routes
    window.open(url, '_blank');
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      {/* Header */}
      <div>
        <h1 className="text-largeTitle font-bold gold-gradient-text">System & Monitoring</h1>
        <p className="text-body text-gray-600 dark:text-gray-400 mt-1">
          Access all system services and monitoring tools
        </p>
      </div>

      {/* Services Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {services.map((service, index) => {
          const Icon = service.icon;
          return (
            <motion.div
              key={service.name}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              className="ios-card p-6 hover:shadow-ios-hover transition-shadow duration-300 cursor-pointer group"
              onClick={() => openService(service.url)}
            >
              <div className="flex items-start justify-between mb-4">
                <div className={`p-3 rounded-ios bg-${service.color}/10`}>
                  <Icon className={`w-6 h-6 text-${service.color}`} />
                </div>
                <ExternalLink className="w-5 h-5 text-gray-400 group-hover:text-gold transition-colors" />
              </div>

              <h3 className="text-title3 font-semibold mb-2">{service.name}</h3>
              <p className="text-body text-gray-600 dark:text-gray-400 mb-4">
                {service.description}
              </p>

              <div className="flex items-center gap-2 text-caption text-gray-500">
                <div className="w-2 h-2 rounded-full bg-ios-green animate-pulse" />
                <span>Port {service.port}</span>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Quick Stats */}
      <div className="ios-card p-6 mt-6">
        <h2 className="text-title2 font-semibold mb-4">System Overview</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-caption text-gray-500 dark:text-gray-400">Services Running</p>
            <p className="text-title2 font-bold text-ios-green mt-1">9/9</p>
          </div>
          <div>
            <p className="text-caption text-gray-500 dark:text-gray-400">Backend Status</p>
            <p className="text-title2 font-bold text-ios-green mt-1">Healthy</p>
          </div>
          <div>
            <p className="text-caption text-gray-500 dark:text-gray-400">Database</p>
            <p className="text-title2 font-bold text-ios-blue mt-1">PostgreSQL</p>
          </div>
          <div>
            <p className="text-caption text-gray-500 dark:text-gray-400">Cache</p>
            <p className="text-title2 font-bold text-ios-blue mt-1">Redis</p>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default System;
