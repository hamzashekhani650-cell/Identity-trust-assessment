import os
import time
import glob
import pandas as pd
from trust_engine import TrustEngine

class SFTPBatchPoller:
    def __init__(self, engine, input_dir="./sftp_input", output_dir="./sftp_processed", interval_seconds=60):
        self.engine = engine
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.interval = interval_seconds
        
        # Make sure directories exist
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def start(self):
        print(f"[SFTP] Poller started. Watching '{self.input_dir}' every {self.interval} seconds...")
        while True:
            self._scan_and_process()
            time.sleep(self.interval)

    def _scan_and_process(self):
        # Find all CSV files in the input directory
        csv_files = glob.glob(os.path.join(self.input_dir, "*.csv"))
        
        for filepath in csv_files:
            filename = os.path.basename(filepath)
            print(f"[SFTP] Found new file: {filename}")
            
            try:
                # 1. Read the CSV
                df = pd.read_csv(filepath)
                
                # 2. Process each record through the Trust Engine
                results = []
                for index, row in df.iterrows():
                    record_dict = row.to_dict()
                    decision = self.engine.assess_record(record_dict)
                    results.append(decision)
                
                # 3. Save the results
                output_path = os.path.join(self.output_dir, f"processed_{filename}")
                pd.DataFrame(results).to_csv(output_path, index=False)
                print(f"[SFTP] Successfully processed {len(results)} records -> {output_path}")
                
                # 4. Move the original file to an archive folder so we don't process it again
                archive_path = os.path.join(self.output_dir, f"original_{filename}")
                os.rename(filepath, archive_path)
                
            except Exception as e:
                print(f"[SFTP] Error processing {filename}: {e}")
                # Move the failed file so we don't get stuck in a loop
                failed_path = os.path.join(self.output_dir, f"failed_{filename}")
                os.rename(filepath, failed_path)

if __name__ == '__main__':
    # Initialize the engine
    engine = TrustEngine(region_profile='UAE (DOH)')
    
    # Initialize the poller (checks every 10 seconds for testing)
    poller = SFTPBatchPoller(engine, interval_seconds=10)
    poller.start()
