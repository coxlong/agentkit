package s3x

import (
	"fmt"
	"os"
	"path/filepath"
)

// atomicWrite writes a file atomically: it writes a temp file in the same
// directory, fsyncs it, then renames it over the target. A crash mid-way leaves
// at most a temp file behind and never corrupts the target. Missing parent
// directories are created automatically.
func atomicWrite(path string, data []byte, perm os.FileMode) error {
	dir, base := filepath.Dir(path), filepath.Base(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("failed to create directory %s: %w", dir, err)
	}
	tmp, err := os.CreateTemp(dir, "."+base+".tmp")
	if err != nil {
		return fmt.Errorf("failed to write %s: %w", path, err)
	}
	tmpName := tmp.Name()
	// After a successful rename the path no longer exists, so this cleanup only
	// fails harmlessly.
	defer os.Remove(tmpName)

	if err := tmp.Chmod(perm); err != nil {
		tmp.Close()
		return fmt.Errorf("failed to set permissions on %s: %w", path, err)
	}
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return fmt.Errorf("failed to write %s: %w", path, err)
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return fmt.Errorf("failed to sync %s: %w", path, err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("failed to write %s: %w", path, err)
	}
	if err := os.Rename(tmpName, path); err != nil {
		return fmt.Errorf("failed to write %s: %w", path, err)
	}
	return nil
}
