""" IntelGPUTop class, encapsulates data from intel_gpu_top utility
"""

from subprocess import Popen, run, PIPE, CalledProcessError
from re import findall
import json
from threading import Thread, Lock

class IntelGPUTop:
    def __init__(self):
        self.lock = Lock()
        self.count = 0
        command = r'lspci -vvnn | grep -A 2 "\[0300\]" | grep -A 2 Intel'
        intel_gpu_data = run([command], shell=True, check=True, stdout=PIPE, stderr=PIPE)
        intel_gpu_data = intel_gpu_data.stdout
        intel_gpu_data = intel_gpu_data.decode('utf-8').split("\n--\n")
        self.count = len(intel_gpu_data)
        pattern = r"\[(\w{4}:\w{4})\]"
        intel_devs = []
        intel_subvens = []
        for intel_gpu in intel_gpu_data:
            vendev, subvendev = findall(pattern=pattern, string=intel_gpu)
            intel_devs.append(vendev.split(":")[1])
            intel_subvens.append(subvendev.split(":")[0])
        command = "sudo intel_gpu_top -L | grep 8086 | awk '{print $3}'"
        intel_pci_strs = run([command], shell=True, check=True, stdout=PIPE, stderr=PIPE)
        intel_pci_strs = intel_pci_strs.stdout.decode('utf-8').split("\n")
        intel_pci_strs = [x for x in intel_pci_strs if x]
        self.data = {}
        for i in range(self.count):
            name = f"Device_{str(intel_devs[i])}-{i}"
            command = f"cat inteldevids | grep -i \"{intel_devs[i]},\""
            try:
                output = run([command],
                             shell=True,
                             check=True,
                             stdout=PIPE,
                             stderr=PIPE).stdout.decode('utf-8')
                output = output.replace("\n", "")
                name = f"{output[5:]}-{i}"
            except CalledProcessError:
                pass

            subven = str(intel_subvens[i])
            command = f"cat venids | grep -i \"{subven},\""
            try:
                output = run([command],
                             shell=True,
                             check=True,
                             stdout=PIPE,
                             stderr=PIPE).stdout.decode('utf-8')
                subven = output[5:]
            except CalledProcessError:
                pass
            self.data[name] = {}

        self.running = True
        self.threads = []
        for pci_str in intel_pci_strs:
            self.threads.append(Thread(target=self.monitor, args=(pci_str,name)))
        for thread in self.threads:
            thread.start()

    def monitor(self, dev, name):
        with Popen(['sudo', 'intel_gpu_top', '-J', '-s', '10000', '-d', dev],
                   stdout=PIPE,
                   stderr=PIPE,
                   text=True,
                   bufsize=1,
                   universal_newlines=True) as process:
            sample = ""
            balance = 0
            started = False  # This flag will help us ignore data until the first {
            for line in iter(process.stdout.readline, ''):
                print(line)
                if not self.running:
                    process.terminate()
                    return

                if '{' in line:
                    started = True

                if not started:
                    continue

                sample += line
                balance += line.count('{') - line.count('}')

                print(balance)
                if balance == 0:
                    # Extract samples from the sample string by splitting it at the comma
                    # followed by an open brace
                    samples = sample.strip('[]').split('},{')
                    samples = ['{' + s + '}' for s in samples]
                    for single_sample in samples:
                        with open("single_sample", 'a', encoding='utf-8') as file:
                            file.write(single_sample)
                        with self.lock:
                            self.data[name] = json.loads(single_sample)
                    sample = ""
                    started = False
            error_output = process.stderr.read()
            if error_output:
                print("Error:", error_output)

    def get_gpu_names(self):
        return list(self.data.keys())

    def print_data(self):
        print(self.data)

    # Period methods
    def get_period_duration(self, name):
        with self.lock:
            ret = self.data[name].get('period', {})
            return ret.get('duration', None)

    def get_period_unit(self, name):
        with self.lock:
            ret = self.data[name].get('period', {})
            return ret.get('unit', None)

    # Frequency methods
    def get_frequency_requested(self, name):
        with self.lock:
            ret = self.data[name].get('frequency', {})
            return ret.get('requested', None)

    def get_frequency_actual(self, name):
        with self.lock:
            return self.data[name]['frequency']['actual']

    def get_frequency_unit(self, name):
        with self.lock:
            return self.data[name]['frequency']['unit']

    # Interrupts methods
    def get_interrupts_count(self, name):
        with self.lock:
            return self.data[name]['interrupts']['count']

    def get_interrupts_unit(self, name):
        with self.lock:
            return self.data[name]['interrupts']['unit']

    # rc6 methods
    def get_rc6_value(self, name):
        with self.lock:
            return self.data[name]['rc6']['value']

    def get_rc6_unit(self, name):
        with self.lock:
            return self.data[name]['rc6']['unit']

    # Power methods
    def get_power_GPU(self, name):
        with self.lock:
            return self.data[name]['power']['GPU']

    def get_power_package(self, name):
        with self.lock:
            return self.data[name]['power']['Package']

    def get_power_unit(self, name):
        with self.lock:
            return self.data[name]['power']['unit']

    # Engines methods
    def get_engine_data(self, name, engine_name):
        with self.lock:
            return self.data[name]['engines'].get(engine_name, {})

    def stop_monitoring(self):
        self.running = False
        for thread in self.threads:
            thread.join()

    def __del__(self):
        self.stop_monitoring()
