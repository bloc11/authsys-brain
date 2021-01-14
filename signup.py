
import main, base64, py, os, time, json
from authsys_common.scripts import get_db_url, get_config
from authsys_common.model import members, daily_passes
from authsys_common import queries as q

from sqlalchemy import select, func

from txrestapi.resource import APIResource
from txrestapi import methods

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.server import NOT_DONE_YET
from twisted.internet import reactor

import treq
# 62617379690

banks = {
   'absa bank': ('Absa Bank', 632005),
   'capitec bank': ('Capitec Bank', 470010),
   'first national bank (south africa)': ('First National Bank (South Africa)', 250655),
   'investec bank': ('Investec Bank', 580105),
   'nedbank (south africa)': ('Nedbank (South Africa)', 198765),
   'nedbank corporate saver account': ('Nedbank Corporate Saver Account', 720026),
   'postbank': ('Postbank', 460005),
   'standard bank (south africa)': ('Standard Bank (South Africa)', 51001),
   'african bank': ('African Bank', 430000),
   'albaraka bank': ('Albaraka Bank', 800000),
   'bank of namibia': ('Bank Of Namibia', 980172),
   'bidvest bank': ('Bidvest Bank', 462005),
   'central bank of lesotho': ('Central Bank Of Lesotho', 586611),
   'citi bank': ('Citi Bank', 350005),
   'finbond mutual bank': ('Finbond Mutual Bank', 589000),
   'first national bank lesotho': ('First National Bank Lesotho', 280061),
   'first national bank namibia': ('First National Bank Namibia', 282672),
   'first national bank swaziland': ('First National Bank Swaziland', 287364),
   'grinrod bank': ('Grinrod Bank', 584000),
   'hsbc bank': ('Hsbc Bank', 587000),
   'jp morgan chase bank': ('Jp Morgan Chase Bank', 432000),
   'meeg bank': ('Meeg Bank', 471001),
   'merchantile bank': ('Merchantile Bank', 450105),
   'mtn banking': ('Mtn Banking', 490991),
   'standard bank namibia': ('Standard Bank Namibia', 87373),
   'state bank of india': ('State Bank Of India', 801000),
   'ubank': ('Ubank', 431010),
   'unibank': ('Unibank', 790005),
   'vbs mutual bank': ('Vbs Mutual Bank', 588000)
}


class CurrentRequestData(object):
    current_request = [None] * 10

    def update(self, request):
        gym_id = int(request.args['gym_id'][0])
        if self.current_request[gym_id] is not None:
            try:
                self.current_request[gym_id].write("{}")
                self.current_request[gym_id].finish()
            except Exception as e:
                print("Error occured: " + str(e))
                # eat all the exceptions here
        self.current_request[gym_id] = request

    def notify(self, **kwds):
        gym_id = int(kwds['gym_id'])
        if self.current_request[gym_id] is None:
            print("No request")
            return
        d = kwds.copy()
        d['redirect'] = kwds.get('type')
        try: # maybe the request was stale
            self.current_request[gym_id].write(json.dumps(d))
            self.current_request[gym_id].finish()
        except:
            print("Found stale request, not notifying")
        finally:
            self.current_request[gym_id] = None


current_request_data = CurrentRequestData()
request_submitted_data = CurrentRequestData() # polling for the main website


class SignupManager(APIResource):
    def __init__(self, arg):
        APIResource.__init__(self)

    @methods.POST('^/signup/submit$')
    def submit(self, request):
        r = main.con.execute(members.insert().values({
            'name': request.args['name'][0].decode('utf8') + u" " + request.args['surname'][0].decode('utf8'),
            'email': request.args['email'][0],
            'phone': request.args['phone'][0],
            'emergency_phone': request.args['emergency-phone'][0],
            'spam_consent': request.args.get('spam', 'off')[0] == u'on',
            'id_number': request.args['id_no'][0],
            'signature_filename': request.args['filename'][0],
            'show_up_reason': request.args['reason'][0],
            'timestamp': int(time.time()),
        }))
        member_id = r.lastrowid
        try:
            int(request.args['gym_id'][0])
        except (KeyError, ValueError):
            gym_id = "null"
        else:
            main.con.execute(daily_passes.insert().values({
                'member_id': member_id,
                'gym_id': int(request.args['gym_id'][0]),
                'timestamp': int(time.time())
                }))
            gym_id = request.args['gym_id'][0]
        #thread.start_new_thread(send_email, (request.args['email'],))
        return py.path.local(__file__).join('..', 'web', 'thankyou.html').read().replace(
            "{{name}}", request.args['name'][0]).replace(
            "{{member_id}}", str(member_id)).replace(
            "{{gym_id}}", gym_id)

    @methods.POST('^/signup/photo')
    def upload_photo(self, request):
        d = request.content.read()
        args = {}
        l = request.uri.split("?")[1].split("=")
        for i in range(0, len(l), 2):
            args[l[i]] = l[i + 1]
        member_id = args['member_id']
        prefix = "data:image/png;base64,"
        assert d.startswith(prefix)
        store_dir = get_config().get('data', 'store_dir')
        # invent new filename
        base_no = member_id
        no = base_no
        fname = os.path.join(store_dir, "photo_%s.png" % no)
        count = 1
        while os.path.exists(fname):
            no = base_no + "_" + str(count)
            fname = os.path.join(store_dir, "photo_%s.png" % no)
            count += 1
        d = d[len(prefix):]
        if (len(d) % 4) != 0:
            d += "=" * (4 - (len(d) % 4))
        with open(fname, "w") as f:
            f.write(base64.b64decode(d, " /"))
        print(member_id, fname)
        main.con.execute(members.update().where(members.c.id == member_id).values(
            photo=fname))
        return json.dumps({'success': True, 'filename': fname, 'member_id': member_id})

    @methods.GET('^/signup/get_photo')
    def get_photo(self, request):
        member_id = request.args['member_id'][0]
        lst = list(main.con.execute(select([members.c.photo]).where(members.c.id == member_id)))
        if lst[0][0] is None:
            return ''
        with open(lst[0][0]) as f:
            return f.read()

    @methods.POST('^/signup/poll')
    def poll(self, request):
        current_request_data.update(request)
        return NOT_DONE_YET

    @methods.POST('^/signup/poll_main')
    def poll_main(self, request):
        request_submitted_data.update(request)
        return NOT_DONE_YET

    @methods.POST('^/signup/notify_picture')
    def notify_picture(self, request):
        gym_id = request.args['gym_id'][0]
        member_id = request.args['member_id'][0]
        current_request_data.notify(gym_id=gym_id, member_id=member_id, type='photo')
        return json.dumps({'success': True})

    @methods.POST('^/signup/notify')
    def notify(self, request):
        name = request.args['name'][0]
        contact_no = request.args['contact_number'][0]
        current_request_data.notify(gym_id=request.args['gym_id'][0], name=name,
            contact_number=contact_no,
            member_id=request.args['member_id'][0], price=request.args['price'][0],
            subscription_type=request.args['subscription_type'][0],
            next_monday=request.args['next_monday'][0], type='bank')
        return json.dumps({'success': True})

    @methods.GET('^/signup/check_bank_account')
    def check_bank_account(self, request):
        def cont2(r):
            request.write(json.dumps(r))
            request.finish()

        def cont1(r):
            d = r.json()
            d.addCallback(cont2)

        account_type = request.args['account_type'][0]
        branch_code = request.args['branch_code'][0]
        account_number = request.args['account_number'][0]
        d = treq.get('https://freecdv.co.za/check/%s/%s/%s' % (account_type, branch_code, account_number))
        d.addCallback(cont1)
        return NOT_DONE_YET

    @methods.POST('^/signup/submit_bank_details')
    def bank_account_update(self, request):
        id = request.args['member_id'][0]
        name = request.args['name'][0]
        contact_number = request.args['contact-number'][0]
        address = request.args['address'][0]
        price = request.args['price'][0]
        branch_code = banks[request.args['bank'][0]][1]
        account_number = request.args['bank-account'][0]
        url = "/".join(request.prePathURL().split("/")[:3]) + "/notify"
        q.update_account_number(main.con, id, name, price, contact_number, address, branch_code, account_number)
        treq.request("POST", url, headers={"Content-Type": "application/json"}, json={"procedure": "com.notify"})
        # generate a PDF in a separate thread with all the information
        return py.path.local(__file__).join('..', 'web', 'thankyou-bank.html').read()

    @methods.GET('^/signup/thankyou_photo')
    def thankyou_photo(self, request):
        request_submitted_data.notify(gym_id=request.args['gym_id'][0], type='photo')
        return py.path.local(__file__).join('..', 'web', 'thankyou_photo.html').read().replace(
            '{{who}}', request.args['name'][0]).replace('{{gym_id}}', request.args['gym_id'][0])

    @methods.POST('^/signup/upload_signature')
    def upload_signature(self, request):
        d = request.content.read()
        prefix = "data:image/png;base64,"
        assert d.startswith(prefix)
        store_dir = get_config().get('data', 'store_dir')
        # invent new filename
        no = list(main.con.execute(select([func.count(members)])))[0][0]
        fname = os.path.join(store_dir, "signature_%d.png" % int(no))
        d = d[len(prefix):]
        if (len(d) % 4) != 0:
            d += "=" * (4 - (len(d) % 4))
        with open(fname, "w") as f:
            f.write(base64.b64decode(d, " /"))
        return fname

