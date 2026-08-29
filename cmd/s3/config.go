package main

import (
	"errors"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/charmbracelet/huh"
	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/coxlong/agentkit/internal/s3x"
)

// errCanceled means the user exited an interactive form (Ctrl+C). main prints
// just "canceled" for it, not the "error:" prefix.
var errCanceled = errors.New("canceled")

var configCmd = &cobra.Command{
	Use:   "config",
	Short: "Configure S3 services and buckets (interactive)",
	Long: `Browse and edit the S3 services and the buckets that belong to each of them.

The menu mirrors the config shape: the top level lists S3 services, and a
service's screen shows its buckets. Selecting a service or bucket is what
scopes the next action — add a bucket to the current service, edit the entry
you are standing on. The agent sees only buckets; this menu is for the operator.`,
	Args: cobra.NoArgs,
	RunE: runConfigMenu,
}

// --- hierarchical interactive menu ---
//
// The menu is a browser over the config, mirroring its shape: services are the
// top level, buckets live under the service they belong to. There is no
// "pick an action, then pick a target" detour — selecting a service or bucket
// scopes the next action to it. The current config stays visible on the screen
// so the operator always knows what they are editing.
//
// Flow:
//
//	services list ─► service detail ─► bucket edit
//	   │                  │
//	   + Add service      + Add bucket / Edit / Delete a service
//
// A selection that is not one of the following action values is a service or
// bucket name to open. Bucket names are validated S3 names and service names
// cannot contain the NUL byte, so the prefix is unambiguous.

const (
	actAddService = "\x00add-service" // top level: add a service
	actAddBucket  = "\x00add-bucket"  // service detail: add a bucket to it
	actEdit       = "\x00edit"        // edit the service or bucket currently selected
	actDelete     = "\x00delete"      // delete the service or bucket currently selected
	actBack       = "\x00back"        // leave the current screen
	actDone       = "\x00done"        // leave the menu entirely
)

// runConfigMenu drives the interactive browser. It never returns an error:
// Ctrl+C cancels cleanly, and an action's validation failure is shown in place
// and the menu stays open.
func runConfigMenu(cmd *cobra.Command, _ []string) error {
	if !term.IsTerminal(int(os.Stdin.Fd())) {
		return errors.New("not an interactive terminal; the config menu is interactive; please run in a terminal")
	}
	for {
		sel, err := serviceList()
		if err != nil {
			if errors.Is(err, errCanceled) {
				return nil
			}
			return err
		}
		switch sel {
		case actDone:
			return nil
		case actAddService:
			if err := menuAddService(cmd); err != nil && !errors.Is(err, errCanceled) {
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
			}
		default:
			if err := serviceDetail(cmd, sel); err != nil && !errors.Is(err, errCanceled) {
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
			}
		}
	}
}

// serviceList shows the top level: every S3 service plus "add" and "done". A
// selected option is either an action constant or a service name to open.
func serviceList() (string, error) {
	cfg, err := s3x.Load()
	if err != nil {
		return "", err
	}
	names := sortedServiceNames(cfg)

	opts := make([]huh.Option[string], 0, len(names)+2)
	for _, n := range names {
		svc := cfg.Services[n]
		opts = append(opts, huh.NewOption(serviceListLabel(n, svc, bucketCount(cfg, n)), n))
	}
	opts = append(opts,
		huh.NewOption("Add a new S3 service", actAddService),
		huh.NewOption("Done", actDone),
	)

	var choice string
	if err := huh.NewSelect[string]().Title("S3 configuration — services").Options(opts...).Value(&choice).Run(); err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			return "", errCanceled
		}
		return "", fmt.Errorf("failed to read input: %w", err)
	}
	return choice, nil
}

// serviceDetail browses one service: its fields are the header, its buckets are
// the entries to open, and the remaining actions operate on the service itself.
func serviceDetail(cmd *cobra.Command, name string) error {
	for {
		sel, err := serviceMenu(name)
		if err != nil {
			if errors.Is(err, errCanceled) {
				return nil // back to the service list
			}
			return err
		}
		switch sel {
		case actBack:
			return nil
		case actAddBucket:
			if err := menuAddBucket(cmd, name); err != nil && !errors.Is(err, errCanceled) {
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
			}
		case actEdit:
			if err := menuEditService(cmd, name); err != nil && !errors.Is(err, errCanceled) {
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
			}
		case actDelete:
			if err := menuRmService(cmd, name); err != nil {
				if errors.Is(err, errCanceled) {
					continue
				}
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
			} else {
				return nil // deleted → back to the service list
			}
		default: // a bucket name
			if err := bucketDetail(cmd, sel); err != nil && !errors.Is(err, errCanceled) {
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
			}
		}
	}
}

func serviceMenu(name string) (string, error) {
	cfg, err := s3x.Load()
	if err != nil {
		return "", err
	}
	svc, ok := cfg.Services[name]
	if !ok {
		return "", fmt.Errorf("service %q does not exist", name)
	}

	opts := make([]huh.Option[string], 0, len(cfg.Buckets)+4)
	for i := range cfg.Buckets {
		b := &cfg.Buckets[i]
		if b.Service != name {
			continue
		}
		opts = append(opts, huh.NewOption(bucketOptionLabel(b), b.Name()))
	}
	opts = append(opts,
		huh.NewOption("Add a bucket", actAddBucket),
		huh.NewOption("Edit this service", actEdit),
		huh.NewOption("Delete this service", actDelete),
		huh.NewOption("← Back", actBack),
	)

	var choice string
	if err := huh.NewSelect[string]().Title(serviceHeader(name, svc)).Options(opts...).Value(&choice).Run(); err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			return "", errCanceled
		}
		return "", fmt.Errorf("failed to read input: %w", err)
	}
	return choice, nil
}

// bucketDetail edits one bucket. Editing re-renders the (possibly renamed)
// bucket; deleting returns to the service detail.
func bucketDetail(cmd *cobra.Command, name string) error {
	for {
		sel, err := bucketMenu(name)
		if err != nil {
			if errors.Is(err, errCanceled) {
				return nil // back to the service detail
			}
			return err
		}
		switch sel {
		case actBack:
			return nil
		case actEdit:
			if err := menuEditBucket(cmd, name); err != nil && !errors.Is(err, errCanceled) {
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
			}
		case actDelete:
			if err := menuRmBucket(cmd, name); err != nil {
				if errors.Is(err, errCanceled) {
					continue
				}
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
			} else {
				return nil // deleted → back to the service detail
			}
		default:
			return fmt.Errorf("unexpected selection %q", sel)
		}
	}
}

func bucketMenu(name string) (string, error) {
	cfg, err := s3x.Load()
	if err != nil {
		return "", err
	}
	idx := bucketIndex(cfg, name)
	if idx < 0 {
		return "", fmt.Errorf("bucket %q does not exist", name)
	}
	b := &cfg.Buckets[idx]

	opts := []huh.Option[string]{
		huh.NewOption("Edit this bucket", actEdit),
		huh.NewOption("Delete this bucket", actDelete),
		huh.NewOption("← Back", actBack),
	}

	var choice string
	if err := huh.NewSelect[string]().Title(bucketHeader(b)).Options(opts...).Value(&choice).Run(); err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			return "", errCanceled
		}
		return "", fmt.Errorf("failed to read input: %w", err)
	}
	return choice, nil
}

// --- list labels and headers ---

func serviceListLabel(name string, svc s3x.Service, nBuckets int) string {
	return fmt.Sprintf("%s   %s · %d bucket(s)", name, endpointLabel(svc), nBuckets)
}

func serviceHeader(name string, svc s3x.Service) string {
	return fmt.Sprintf("%s   endpoint: %s   region: %s   secret: %s",
		name, endpointLabel(svc), svc.Region, secretConfigured(name))
}

// bucketOptionLabel is a bucket's entry in a service's list: the agent-visible
// name with the description appended when present.
func bucketOptionLabel(b *s3x.Bucket) string {
	label := b.Name()
	if b.Desc != "" {
		label += "  (" + b.Desc + ")"
	}
	return label
}

func bucketHeader(b *s3x.Bucket) string {
	line := fmt.Sprintf("%s   bucket: %s   service: %s", b.Name(), b.Bucket, b.Service)
	if b.Desc != "" {
		line += "\n" + b.Desc
	}
	return line
}

func endpointLabel(svc s3x.Service) string {
	if svc.Endpoint == "" {
		return "AWS official endpoint"
	}
	return svc.Endpoint
}

func bucketCount(cfg *s3x.Config, svcName string) int {
	n := 0
	for i := range cfg.Buckets {
		if cfg.Buckets[i].Service == svcName {
			n++
		}
	}
	return n
}

// bucketNamesOf returns the agent-visible names of a service's buckets, in
// config order.
func bucketNamesOf(cfg *s3x.Config, svcName string) []string {
	var names []string
	for i := range cfg.Buckets {
		if cfg.Buckets[i].Service == svcName {
			names = append(names, cfg.Buckets[i].Name())
		}
	}
	return names
}

// secretConfigured reports whether the service has a non-empty secret, without
// printing it. It tolerates an undecryptable secrets file and shows "?".
func secretConfigured(name string) string {
	secrets, err := s3x.LoadSecrets(s3x.SecretsPath())
	if err != nil {
		return "?"
	}
	if s, ok := secrets[name]; ok && s.SecretAccessKey != "" {
		return "configured"
	}
	return "missing"
}

// --- service actions ---

func menuAddService(cmd *cobra.Command) error {
	var name, endpoint, region, ak, pathStyle, sk string
	ask := &asker{}
	ask.text(&name, "S3 service name", "a short name, e.g. minio or aliyun").Validate(notEmpty)
	ask.text(&endpoint, "Endpoint", "leave empty to use the AWS official endpoint")
	ask.text(&region, "Region", "leave empty for us-east-1")
	ask.text(&ak, "Access Key ID", "").Validate(notEmpty)
	ask.pathStyle(&pathStyle)
	ask.password(&sk, "Secret Access Key")
	if err := ask.run(); err != nil {
		return err
	}
	if region == "" {
		region = "us-east-1"
	}
	cfg, err := s3x.Load()
	if err != nil {
		return err
	}
	if err := addService(cfg, name, endpoint, region, ak, parsePathStyle(pathStyle), sk); err != nil {
		return err
	}
	fmt.Fprintf(cmd.OutOrStdout(), "Service %q saved\n", name)
	return nil
}

func menuEditService(cmd *cobra.Command, svcName string) error {
	cfg, err := s3x.Load()
	if err != nil {
		return err
	}
	svc, ok := cfg.Services[svcName]
	if !ok {
		return fmt.Errorf("service %q does not exist", svcName)
	}
	endpoint, region, ak := svc.Endpoint, svc.Region, svc.AccessKeyID
	pathStyle := pathStyleLabel(svc)
	var newSecret string

	ask := &asker{}
	ask.text(&endpoint, "Endpoint", "leave empty to use the AWS official endpoint")
	ask.text(&region, "Region", "leave empty for us-east-1")
	ask.text(&ak, "Access Key ID", "")
	ask.pathStyle(&pathStyle)
	ask.passwordOptional(&newSecret, "Secret Access Key", "leave empty to keep the existing secret")
	if err := ask.run(); err != nil {
		return err
	}
	if region == "" {
		region = "us-east-1"
	}
	if err := updateService(cfg, svcName, endpoint, region, ak, parsePathStyle(pathStyle), newSecret); err != nil {
		return err
	}
	fmt.Fprintf(cmd.OutOrStdout(), "Service %q updated\n", svcName)
	return nil
}

func menuRmService(cmd *cobra.Command, svcName string) error {
	cfg, err := s3x.Load()
	if err != nil {
		return err
	}
	if _, ok := cfg.Services[svcName]; !ok {
		return fmt.Errorf("service %q does not exist", svcName)
	}
	names := bucketNamesOf(cfg, svcName)
	msg := fmt.Sprintf("Delete service %q and its secret?", svcName)
	if len(names) > 0 {
		msg = fmt.Sprintf("Delete service %q and its secret?\nIt has %d bucket(s): %s. They are removed too.", svcName, len(names), strings.Join(names, ", "))
	}
	ok, err := confirm(msg)
	if err != nil {
		return err
	}
	if !ok {
		return nil
	}
	if err := deleteService(cfg, svcName); err != nil {
		return err
	}
	if len(names) > 0 {
		fmt.Fprintf(cmd.OutOrStdout(), "Service %q and %d bucket(s) deleted\n", svcName, len(names))
	} else {
		fmt.Fprintf(cmd.OutOrStdout(), "Service %q deleted\n", svcName)
	}
	return nil
}

// --- bucket actions ---

func menuAddBucket(cmd *cobra.Command, service string) error {
	cfg, err := s3x.Load()
	if err != nil {
		return err
	}
	if _, ok := cfg.Services[service]; !ok {
		return fmt.Errorf("service %q does not exist", service)
	}

	var bucket, alias, desc string
	ask := &asker{}
	ask.text(&bucket, "Real bucket name", "the S3 bucket name").Validate(notEmpty)
	ask.text(&alias, "Agent-visible short name", "leave empty to use the bucket name")
	ask.text(&desc, "Description", "for the agent; describe the purpose and data lifecycle")
	if err := ask.run(); err != nil {
		return err
	}
	if err := addBucket(cfg, bucket, alias, service, desc); err != nil {
		return err
	}
	fmt.Fprintf(cmd.OutOrStdout(), "Bucket %q saved\n", nameFor(bucket, alias))
	return nil
}

func menuEditBucket(cmd *cobra.Command, bName string) error {
	cfg, err := s3x.Load()
	if err != nil {
		return err
	}
	idx := bucketIndex(cfg, bName)
	if idx < 0 {
		return fmt.Errorf("bucket %q does not exist", bName)
	}
	b := cfg.Buckets[idx]
	bucket, alias := b.Bucket, b.Alias
	desc := b.Desc
	service := b.Service

	ask := &asker{}
	ask.text(&bucket, "Real bucket name", "the S3 bucket name").Validate(notEmpty)
	ask.text(&alias, "Agent-visible short name", "leave empty to use the bucket name")
	ask.selectValue(&service, "S3 service", "the service this bucket belongs to", serviceOpts(cfg))
	ask.text(&desc, "Description", "for the agent; describe the purpose and data lifecycle")
	if err := ask.run(); err != nil {
		return err
	}
	if err := updateBucket(cfg, bName, bucket, alias, service, desc); err != nil {
		return err
	}
	fmt.Fprintf(cmd.OutOrStdout(), "Bucket %q updated\n", nameFor(bucket, alias))
	return nil
}

func menuRmBucket(cmd *cobra.Command, bName string) error {
	cfg, err := s3x.Load()
	if err != nil {
		return err
	}
	idx := bucketIndex(cfg, bName)
	if idx < 0 {
		return fmt.Errorf("bucket %q does not exist", bName)
	}
	ok, err := confirm(fmt.Sprintf("Delete bucket %q?", bName))
	if err != nil {
		return err
	}
	if !ok {
		return nil
	}
	if err := deleteBucket(cfg, bName); err != nil {
		return err
	}
	fmt.Fprintf(cmd.OutOrStdout(), "Bucket %q deleted\n", bName)
	return nil
}

// --- selection helpers ---

// serviceOpts lists the configured S3 services, for the "move bucket to another
// service" choice during an edit.
func serviceOpts(cfg *s3x.Config) []huh.Option[string] {
	names := sortedServiceNames(cfg)
	opts := make([]huh.Option[string], 0, len(names))
	for _, n := range names {
		opts = append(opts, huh.NewOption(n, n))
	}
	return opts
}

func sortedServiceNames(cfg *s3x.Config) []string {
	names := make([]string, 0, len(cfg.Services))
	for n := range cfg.Services {
		names = append(names, n)
	}
	sort.Strings(names)
	return names
}

func bucketIndex(cfg *s3x.Config, name string) int {
	for i := range cfg.Buckets {
		if cfg.Buckets[i].Name() == name {
			return i
		}
	}
	return -1
}

func nameFor(bucket, alias string) string {
	if alias != "" {
		return alias
	}
	return bucket
}

// --- pure config mutations (testable) ---

// addService creates or overwrites a service and its secret.
func addService(cfg *s3x.Config, name, endpoint, region, ak string, forcePathStyle *bool, sk string) error {
	if name == "" {
		return errors.New("service name is required")
	}
	if region == "" {
		region = "us-east-1"
	}
	if cfg.Services == nil {
		cfg.Services = map[string]s3x.Service{}
	}
	if _, exists := cfg.Services[name]; exists {
		fmt.Fprintf(os.Stderr, "warning: service %q already exists; config and secret will be overwritten\n", name)
	}
	cfg.Services[name] = s3x.Service{Endpoint: endpoint, Region: region, AccessKeyID: ak, ForcePathStyle: forcePathStyle}

	// Write the secret first, then the config: a config that saved but the
	// secret did not would leave a "configured but cannot connect" state.
	secrets, err := s3x.LoadSecrets(s3x.SecretsPath())
	if err != nil {
		return err
	}
	secrets[name] = s3x.ServiceSecret{SecretAccessKey: sk}
	if err := s3x.SaveSecrets(s3x.SecretsPath(), secrets); err != nil {
		return err
	}
	return cfg.Save()
}

// updateService overwrites a service's fields; a non-empty newSecret replaces
// the existing secret, otherwise it is kept as-is.
func updateService(cfg *s3x.Config, name, endpoint, region, ak string, forcePathStyle *bool, newSecret string) error {
	if _, ok := cfg.Services[name]; !ok {
		return fmt.Errorf("service %q does not exist", name)
	}
	cfg.Services[name] = s3x.Service{Endpoint: endpoint, Region: region, AccessKeyID: ak, ForcePathStyle: forcePathStyle}

	if newSecret == "" {
		return cfg.Save()
	}
	secrets, err := s3x.LoadSecrets(s3x.SecretsPath())
	if err != nil {
		return err
	}
	secrets[name] = s3x.ServiceSecret{SecretAccessKey: newSecret}
	if err := s3x.SaveSecrets(s3x.SecretsPath(), secrets); err != nil {
		return err
	}
	return cfg.Save()
}

// deleteService removes a service, its secret, and every bucket that belongs to
// it (cascade). Deleting is cascading on purpose: once the service is gone, its
// buckets are dead references pointing at an undefined service, so they are
// removed with it rather than left behind to break config validation.
func deleteService(cfg *s3x.Config, name string) error {
	if _, ok := cfg.Services[name]; !ok {
		return fmt.Errorf("service %q does not exist", name)
	}
	kept := make([]s3x.Bucket, 0, len(cfg.Buckets))
	for i := range cfg.Buckets {
		if cfg.Buckets[i].Service != name {
			kept = append(kept, cfg.Buckets[i])
		}
	}
	cfg.Buckets = kept

	delete(cfg.Services, name)
	if err := cfg.Save(); err != nil {
		return err
	}
	secrets, err := s3x.LoadSecrets(s3x.SecretsPath())
	if err != nil {
		return err
	}
	delete(secrets, name)
	return s3x.SaveSecrets(s3x.SecretsPath(), secrets)
}

// addBucket appends a bucket to the config; Save rejects a duplicate
// agent-visible name.
func addBucket(cfg *s3x.Config, bucket, alias, service, desc string) error {
	if _, ok := cfg.Services[service]; !ok {
		return fmt.Errorf("service %q does not exist", service)
	}
	cfg.Buckets = append(cfg.Buckets, s3x.Bucket{Bucket: bucket, Alias: alias, Service: service, Desc: desc})
	return cfg.Save()
}

// updateBucket replaces the bucket currently addressed by currentName.
func updateBucket(cfg *s3x.Config, currentName, bucket, alias, service, desc string) error {
	if _, ok := cfg.Services[service]; !ok {
		return fmt.Errorf("service %q does not exist", service)
	}
	idx := bucketIndex(cfg, currentName)
	if idx < 0 {
		return fmt.Errorf("bucket %q does not exist", currentName)
	}
	cfg.Buckets[idx] = s3x.Bucket{Bucket: bucket, Alias: alias, Service: service, Desc: desc}
	return cfg.Save()
}

// deleteBucket removes a bucket from the config.
func deleteBucket(cfg *s3x.Config, name string) error {
	idx := bucketIndex(cfg, name)
	if idx < 0 {
		return fmt.Errorf("bucket %q does not exist", name)
	}
	cfg.Buckets = append(cfg.Buckets[:idx], cfg.Buckets[idx+1:]...)
	return cfg.Save()
}

// --- shared form helpers ---

// asker collects a set of fields into a huh form, then asks them all at once
// in run. Fields are trimmed of surrounding whitespace on submit. The menu
// always prompts every field (there are no flags to pre-fill).
type asker struct {
	fields []huh.Field
	bound  []*string
}

func (a *asker) text(dst *string, title, desc string) *huh.Input {
	input := huh.NewInput().Title(title).Value(dst)
	if desc != "" {
		input.Description(desc)
	}
	a.fields = append(a.fields, input)
	a.bound = append(a.bound, dst)
	return input
}

// password is a secret field: it is entered without echo, so it never appears
// in ps output or shell history. It is required.
func (a *asker) password(dst *string, title string) {
	a.text(dst, title, "").Password(true).Validate(notEmpty)
}

// passwordOptional is a masked secret field that may be left empty — used when
// editing, where a blank value means "keep the existing secret".
func (a *asker) passwordOptional(dst *string, title, desc string) {
	input := huh.NewInput().Title(title).Value(dst).Password(true)
	if desc != "" {
		input.Description(desc)
	}
	a.fields = append(a.fields, input)
	a.bound = append(a.bound, dst)
}

// pathStyle asks how to address the service: auto (endpoint set → path-style),
// force path-style, or virtual-hosted-style.
func (a *asker) pathStyle(dst *string) {
	*dst = "auto"
	sel := huh.NewSelect[string]().
		Title("Addressing style").
		Description("auto (endpoint set → path-style), yes (force path-style), or no (virtual-hosted-style)").
		Options(huh.NewOptions("auto", "yes", "no")...).
		Value(dst)
	a.fields = append(a.fields, sel)
	a.bound = append(a.bound, dst)
}

func (a *asker) selectValue(dst *string, title, desc string, opts []huh.Option[string]) {
	sel := huh.NewSelect[string]().Title(title).Options(opts...).Value(dst)
	if desc != "" {
		sel.Description(desc)
	}
	a.fields = append(a.fields, sel)
	a.bound = append(a.bound, dst)
}

func (a *asker) run() error {
	if len(a.fields) == 0 {
		return nil
	}
	if !term.IsTerminal(int(os.Stdin.Fd())) {
		return errors.New("not an interactive terminal; cannot prompt; please run in a terminal")
	}
	if err := huh.NewForm(huh.NewGroup(a.fields...)).Run(); err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			return errCanceled
		}
		return fmt.Errorf("failed to read input: %w", err)
	}
	for _, dst := range a.bound {
		*dst = strings.TrimSpace(*dst)
	}
	return nil
}

func notEmpty(s string) error {
	if strings.TrimSpace(s) == "" {
		return errors.New("must not be empty")
	}
	return nil
}

// confirm pops a confirmation dialog: an affirmative confirms, a negative or
// plain Enter cancels.
func confirm(msg string) (bool, error) {
	if !term.IsTerminal(int(os.Stdin.Fd())) {
		return false, errors.New("not an interactive terminal; cannot confirm; please run in a terminal")
	}
	var ok bool
	if err := huh.NewConfirm().
		Title(msg).
		Affirmative("Confirm").
		Negative("Cancel").
		Value(&ok).
		Run(); err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			return false, errCanceled
		}
		return false, fmt.Errorf("failed to read input: %w", err)
	}
	return ok, nil
}

func parsePathStyle(s string) *bool {
	switch s {
	case "yes":
		v := true
		return &v
	case "no":
		v := false
		return &v
	default: // auto
		return nil
	}
}

func pathStyleLabel(svc s3x.Service) string {
	if svc.ForcePathStyle == nil {
		return "auto"
	}
	if *svc.ForcePathStyle {
		return "yes"
	}
	return "no"
}
